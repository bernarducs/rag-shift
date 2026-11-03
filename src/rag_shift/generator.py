import os

from groq import Groq

from rag_shift.config import SYSTEM_PROMPT


def generate_answer(query: str, docs: list[tuple[float, dict]]) -> str:
    context = "\n\n".join(
        f"[{doc['subject']} - {doc['date'][:10]}]\n{doc['text']}" for _, doc in docs
    )
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=os.environ["MODEL"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexto:\n{context}\n\nPergunta: {query}"},
        ],
    )
    return response.choices[0].message.content
