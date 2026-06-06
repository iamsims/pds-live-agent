"""Quick demo — run a single query through the live finder."""

import asyncio

from dotenv import load_dotenv

load_dotenv()

from pydantic_code.live_finder.pds_finder import run_layered_query


async def main():
    query = "What calibrated spectral data exists for Saturn's rings from Cassini UVIS?"

    print(f"Query: {query}\n")
    decision, output = await run_layered_query(query)

    print(f"Routed to: {decision.primary_node} ({decision.confidence})")
    print(f"Router reasoning: {decision.reasoning}\n")

    for i, c in enumerate(output.candidates, 1):
        print(f"{i}. {c.dataset_id or '(no id)'}")
        if c.path:
            print(f"   path: {c.path}")
        print(f"   {c.reasoning}\n")

    print(f"Summary: {output.summary}")


if __name__ == "__main__":
    asyncio.run(main())
