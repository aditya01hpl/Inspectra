async def format_response(query: str, result: dict, context: list, sources: list):
    prompt = f"""
Query: {query}
SQL Result: {result}
Context from related docs: {context}
Sources: {sources}

Respond clearly, avoid mixing sources with results.
"""

    async with httpx.AsyncClient() as client:
        res = await client.post("http://localhost:11434/api/generate", json={
            "model": "qwen2.5-coder:3b",
            "prompt": prompt,
            "stream": False
        },timeout=60)
        return res.json()