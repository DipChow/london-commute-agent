"""Create an OpenAI client and test the connection."""

import os

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
)

from commute_agent.storage import ROOT

DEFAULT_MODEL = "gpt-5.4-mini-2026-03-17"


def get_ai_client() -> OpenAI:
    """Load local credentials and create a client."""
    load_dotenv(ROOT / ".env", override=False)

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is missing from your .env file.")

    return OpenAI(
        timeout=30.0,
        max_retries=0,
    )


def get_ai_model() -> str:
    """Read the configured model after loading local settings."""
    load_dotenv(ROOT / ".env", override=False)
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def main():
    """Make one small API request to check the connection."""
    try:
        client = get_ai_client()

        response = client.responses.create(
            model=get_ai_model(),
            input="Reply with exactly: API connection working.",
            max_output_tokens=256,
            store=False,
        )

        if response.status != "completed":
            print("The API responded, but the response was incomplete.")
            return

        print(response.output_text)

    except ValueError as error:
        print(error)
    except AuthenticationError:
        print("Authentication failed. Check your API key.")
    except APIConnectionError:
        print("Could not connect to OpenAI. Check your connection.")
    except APIStatusError as error:
        print(
            f"OpenAI returned HTTP {error.status_code}. "
            "Check your project's model access, billing and limits."
        )


if __name__ == "__main__":
    main()