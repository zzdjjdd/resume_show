import requests
response = requests.post(
    "https://api.siliconflow.cn/v1/embeddings",
    headers={
        "Authorization": "Bearer $SILICONFLOW_API_KEY",
        "Content-Type": "application/json"
    },
    json={
        "input": "Hello, world!",
        "model": "Qwen/Qwen3-Embedding-4B"
    }
)
print(response.json())