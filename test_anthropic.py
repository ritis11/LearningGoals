import os
from anthropic import Anthropic

# Ensure you have your API key set in your environment:
os.environ['ANTHROPIC_API_KEY']=''

client = Anthropic()

try:
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=100,
        messages=[
            {"role": "user", "content": "Hello! Please respond with a single word to confirm this is working."}
        ]
    )
    print("Success! Response from Claude:")
    print(message.content[0].text)
except Exception as e:
    print(f"Error: {e}")
