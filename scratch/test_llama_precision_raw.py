from langchain_ollama import ChatOllama

local_llm = ChatOllama(model="llama3", temperature=0.0)

# Recreate Ragas ContextPrecision Prompt
prompt = """Given the following question, context, and answer, verify if the context was useful in arriving at the given answer. Give the verdict as "1" if useful and "0" if not, in JSON format.

Question: Who is a C++ developer with multithreading experience?
Context: Experienced in C++ and multithreading.
Answer: We found candidates with C++ and multithreading experience.

Format the output exactly as:
{
  "reason": "<brief reason>",
  "verdict": 1 or 0
}"""

print("Sending prompt to Llama 3...")
res = local_llm.invoke(prompt)
print("\nLlama 3 Raw Response:")
print(res.content)
