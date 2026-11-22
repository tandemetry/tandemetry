import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from importlib.metadata import version
from typing import Protocol

import uvicorn
from aiokafka.errors import KafkaError
from clickhouse_connect.driver.exceptions import Error as ClickHouseError
from fastapi import FastAPI

from tandemetry.api.app import create_app
from tandemetry.events.consumer import EventConsumer
from tandemetry.events.kafka import kafka_batch_source, kafka_event_publisher
from tandemetry.events.ports import BatchSource, EventPublisher, EventSink
from tandemetry.events.sample import SAMPLE_EVENT
from tandemetry.ingest.github.client import github_api
from tandemetry.ingest.github.kafka import kafka_raw_webhook_publisher, kafka_raw_webhook_source
from tandemetry.ingest.github.normalizer import WebhookNormalizer
from tandemetry.ingest.github.ports import GitHubApi, GitHubApiError, RawWebhookPublisher
from tandemetry.ingest.github.receiver import WebhookReceiver
from tandemetry.ingest.github.retry import GitHubRetry, GitHubStalledError, RetryPolicy
from tandemetry.ingest.github.signature import WebhookSignature
from tandemetry.ingest.github.worker import NormalizerWorker
from tandemetry.settings import (
    ApiSettings,
    ClickHouseSettings,
    GitHubSettings,
    KafkaSettings,
    Settings,
)
from tandemetry.storage.clickhouse import (
    ClickHouseMigrator,
    clickhouse_client,
    clickhouse_event_store,
)

INTERRUPTED_EXIT_CODE = 130


class VersionProvider(Protocol):
    def get(self) -> str: ...


class CommandError(Exception):
    """A command failure reported to the user as one line, without a traceback."""


class Command(Protocol):
    help: str

    async def run(self) -> None: ...


class PackageVersionProvider:
    def __init__(self, package: str = "tandemetry") -> None:
        self._package = package

    def get(self) -> str:
        return version(self._package)


class MigrateCommand:
    help = "apply ClickHouse schema migrations"

    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings

    async def run(self) -> None:
        try:
            async with clickhouse_client(self._settings) as client:
                applied = await ClickHouseMigrator(client).apply()
        except ClickHouseError as error:
            address = f"{self._settings.host}:{self._settings.port}"
            raise CommandError(f"ClickHouse at {address}: {error}") from error
        print(f"applied: {', '.join(applied) or 'nothing'}")


PublisherFactory = Callable[[KafkaSettings], AbstractAsyncContextManager[EventPublisher]]


class PublishSampleCommand:
    help = "publish a fixed sample event to Kafka"

    def __init__(
        self, settings: KafkaSettings, open_publisher: PublisherFactory = kafka_event_publisher
    ) -> None:
        self._settings = settings
        self._open_publisher = open_publisher

    async def run(self) -> None:
        try:
            async with self._open_publisher(self._settings) as publisher:
                await publisher.publish(SAMPLE_EVENT)
        except KafkaError as error:
            raise CommandError(f"Kafka at {self._settings.bootstrap_servers}: {error}") from error
        print(f"published {SAMPLE_EVENT.event_id} to {self._settings.events_topic}")


SourceFactory = Callable[[KafkaSettings], AbstractAsyncContextManager[BatchSource]]
SinkFactory = Callable[[ClickHouseSettings], AbstractAsyncContextManager[EventSink]]


class ConsumeCommand:
    help = "consume events from Kafka into ClickHouse until interrupted"

    def __init__(
        self,
        kafka: KafkaSettings,
        clickhouse: ClickHouseSettings,
        open_source: SourceFactory = kafka_batch_source,
        open_sink: SinkFactory = clickhouse_event_store,
    ) -> None:
        self._kafka = kafka
        self._clickhouse = clickhouse
        self._open_source = open_source
        self._open_sink = open_sink

    async def run(self) -> None:
        try:
            async with (
                self._open_sink(self._clickhouse) as sink,
                self._open_source(self._kafka) as source,
            ):
                print(f"consuming {self._kafka.events_topic} as {self._kafka.consumer_group}")
                await EventConsumer(source, sink).run()
        except KafkaError as error:
            raise CommandError(f"Kafka at {self._kafka.bootstrap_servers}: {error}") from error
        except ClickHouseError as error:
            address = f"{self._clickhouse.host}:{self._clickhouse.port}"
            raise CommandError(f"ClickHouse at {address}: {error}") from error


RawPublisherFactory = Callable[[KafkaSettings], AbstractAsyncContextManager[RawWebhookPublisher]]
Serve = Callable[[FastAPI, ApiSettings], Awaitable[None]]


async def serve_with_uvicorn(app: FastAPI, settings: ApiSettings) -> None:
    """Serve the app until the process receives a stop signal."""
    await uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port)).serve()


class ServeCommand:
    help = "receive GitHub webhooks onto the raw Kafka topic until stopped"

    def __init__(
        self,
        api: ApiSettings,
        github: GitHubSettings,
        kafka: KafkaSettings,
        open_publisher: RawPublisherFactory = kafka_raw_webhook_publisher,
        serve: Serve = serve_with_uvicorn,
    ) -> None:
        self._api = api
        self._github = github
        self._kafka = kafka
        self._open_publisher = open_publisher
        self._serve = serve

    async def run(self) -> None:
        if not self._github.webhook_secret.get_secret_value():
            raise CommandError("set TANDEMETRY_GITHUB__WEBHOOK_SECRET")
        signature = WebhookSignature(self._github.webhook_secret)
        try:
            async with self._open_publisher(self._kafka) as publisher:
                receiver = WebhookReceiver(signature, publisher)
                await self._serve(create_app(receiver, self._api.max_body_bytes), self._api)
        except KafkaError as error:
            raise CommandError(f"Kafka at {self._kafka.bootstrap_servers}: {error}") from error


ApiFactory = Callable[[GitHubSettings], AbstractAsyncContextManager[GitHubApi]]


class NormalizeCommand:
    help = "normalize raw GitHub webhooks into events until interrupted"

    def __init__(
        self,
        kafka: KafkaSettings,
        github: GitHubSettings,
        open_source: SourceFactory = kafka_raw_webhook_source,
        open_publisher: PublisherFactory = kafka_event_publisher,
        open_api: ApiFactory = github_api,
    ) -> None:
        self._kafka = kafka
        self._github = github
        self._open_source = open_source
        self._open_publisher = open_publisher
        self._open_api = open_api

    async def run(self) -> None:
        if not self._github.client_id or not self._github.private_key.get_secret_value():
            raise CommandError(
                "set TANDEMETRY_GITHUB__CLIENT_ID and TANDEMETRY_GITHUB__PRIVATE_KEY"
            )
        retry = GitHubRetry(
            RetryPolicy(
                self._github.retry_initial_s,
                self._github.retry_max_s,
                self._github.rate_limit_max_wait_s,
                self._github.batch_deadline_s,
            )
        )
        try:
            async with (
                self._open_api(self._github) as api,
                self._open_publisher(self._kafka) as publisher,
                self._open_source(self._kafka) as source,
            ):
                print(f"normalizing {self._kafka.raw_topic} as {self._kafka.normalizer_group}")
                await NormalizerWorker(source, WebhookNormalizer(api), publisher, retry).run()
        except KafkaError as error:
            raise CommandError(f"Kafka at {self._kafka.bootstrap_servers}: {error}") from error
        except (GitHubApiError, GitHubStalledError) as error:
            raise CommandError(f"GitHub API at {self._github.api_url}: {error}") from error


class Cli:
    def __init__(
        self,
        version_provider: VersionProvider,
        settings: Settings,
        commands: Mapping[str, Command],
    ) -> None:
        self._commands = commands
        self._parser = argparse.ArgumentParser(prog=settings.app_name)
        self._parser.add_argument(
            "--version",
            action="version",
            version=f"{settings.app_name} {version_provider.get()}",
        )
        subparsers = self._parser.add_subparsers(dest="command")
        for name, command in commands.items():
            subparsers.add_parser(name, help=command.help)

    def run(self, argv: Sequence[str] | None = None) -> int:
        try:
            arguments = self._parser.parse_args(argv)
        except SystemExit as exit_request:
            return exit_request.code if isinstance(exit_request.code, int) else 0
        if arguments.command is None:
            self._parser.print_help()
            return 0
        try:
            asyncio.run(self._commands[arguments.command].run())
        except CommandError as error:
            print(f"{self._parser.prog} {arguments.command}: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return INTERRUPTED_EXIT_CODE
        return 0


def main() -> None:
    settings = Settings()
    commands: dict[str, Command] = {
        "migrate": MigrateCommand(settings.clickhouse),
        "publish-sample": PublishSampleCommand(settings.kafka),
        "consume": ConsumeCommand(settings.kafka, settings.clickhouse),
        "serve": ServeCommand(settings.api, settings.github, settings.kafka),
        "normalize": NormalizeCommand(settings.kafka, settings.github),
    }
    cli = Cli(PackageVersionProvider(), settings, commands)
    raise SystemExit(cli.run())
