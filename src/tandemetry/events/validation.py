from pydantic import ValidationError


def describe(error: ValidationError) -> str:
    """Field locations and error types of a validation error, never the input values."""
    return "; ".join(
        f"{'.'.join(map(str, problem['loc']))}: {problem['type']}"
        for problem in error.errors(include_input=False, include_url=False, include_context=False)
    )
