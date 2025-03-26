import fire
import mlx_lm

def generate(model, prompt, max_tokens):
    model, tokenizer = mlx_lm.load(model)

    messages = [{"role": "user", "content": prompt}]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    response = mlx_lm.generate(
        model,
        tokenizer,
        prompt,
        max_tokens,
    )
    print(response)

if __name__ == "__main__":
    # Default parameters
    model = "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
    prompt = "Write a story about Einstein"
    max_tokens = 256
    
    # Run the generation
    generate(model, prompt, max_tokens)

# You can still run with custom parameters like so:
# HF_HUB_DISABLE_PROGRESS_BARS=1 python generate.py --model mlx-community/Qwen2.5-Coder-14B-Instruct-4bit --prompt "Write a story about Einstein" --max-tokens 256
