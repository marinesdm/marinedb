# Llama to standardize scientific names
   
Use Llama Large Language Model (LLM) to standardize scientific names.
   
## 1. Install dependencies
   
```
pip install PyYAML jinja2 tiktoken pydantic>=2 Pillow torch fairscale fire blobfile accelerate>=0.26.0
pip install --upgrade transformers      
```
   
## 2. Download model
   
### 2.1 Via Meta Llama website (no account required)
   
#### 2.1.1 Download weights
  
The first list below is adapted from [meta-llama](https://github.com/meta-llama/llama-models?tab=readme-ov-file#download) Github.
   
1. Visit the [Meta Llama website](https://www.llama.com/llama-downloads/).
2. Read and accept the license.
3. Since your request is approved you will receive a signed URL via email. Remember that the links expire after 24 hours and a certain amount of downloads. You can always re-request a link if you start seeing errors such as 403: Forbidden.
4. Install the Llama CLI: `pip install llama-stack.`
5. Run `llama model list` to show the latest available models and determine the model ID you wish to download. For the task, use `Llama3.2-3B-Instruct` ID (identifier corresponding to a lightweight model capable of following prompted instructions).
6. Run `llama download --source meta --model-id CHOSEN_MODEL_ID`
7. Pass the URL provided when prompted to start the download.
   
The model will be downloaded to the folder where the command was run. The name of the downloaded folder should be `.llama`. Run `ls -laht` to check that the download was successful. 
   
#### 2.1.2 Convert weights
   
To load the model via the `transformers` package, the downloaded checkpoint must first be converted using `transformers` [Llama conversion script](https://github.com/huggingface/transformers/blob/main/src/transformers/models/llama/convert_llama_weights_to_hf.py) `convert_llama_weights_to_hf.py`: 
1. **PATH1**: Path to the conversion script. Run `pip show transformers` to find out where the `transformers` package is stored (look at the `Location` field). `PATH1` is the concatenation of this path with `transformers/models/llama/convert_llama_weights_to_hf.py`. 
Example: `/opt/venv/ecolab/lib/python3.10/site-packages/transformers/models/llama/convert_llama_weights_to_hf.py`.
2. **PATH2**: Path to the downloaded weights. `PATH2` is the concatenation of the path to the downloaded folder with `checkpoints/Llama3.2-3B-Instruct`. 
Example: `./.llama/checkpoints/Llama3.2-3B-Instruct`.
3. **PATH3**: Path to the folder in which you want to store the ready-to-use model.
Example: `./Llama`
4. Run `python PATH1 --input_dir PATH2 --num_shards 1 --output_dir PATH3 --llama_version 3.2`, replacing `PATH1`, `PATH2` and `PATH3` with their values, as explained in the previous points.   
  
You may want to change the number indicated after the `--num_shards` option depending on the computational resources you have access to. Read [this article](https://medium.com/@pranay.janupalli/understanding-model-sharding-and-model-parallelism-scaling-large-language-models-dee6144d0591) to find out more.
   
Finally, to avoid raising an error when using `transformers` tools (and more specifically the `tokenizer` package), you need to add a line to the `tokenizer_config.json` file in the `PATH3` folder:
1. Open `tokenizer_config.json`.
2. If the `chat_template` attribute is not present at the end of the file, add the following line between `bos_token` and `clean_up_tokenization_spaces` lines:
```
"chat_template": "{{- bos_token }}\n{%- if custom_tools is defined %}\n    {%- set tools = custom_tools %}\n{%- endif %}\n{%- if not tools_in_user_message is defined %}\n    {%- set tools_in_user_message = true %}\n{%- endif %}\n{%- if not date_string is defined %}\n    {%- if strftime_now is defined %}\n        {%- set date_string = strftime_now(\"%d %b %Y\") %}\n    {%- else %}\n        {%- set date_string = \"26 Jul 2024\" %}\n    {%- endif %}\n{%- endif %}\n{%- if not tools is defined %}\n    {%- set tools = none %}\n{%- endif %}\n\n{#- This block extracts the system message, so we can slot it into the right place. #}\n{%- if messages[0]['role'] == 'system' %}\n    {%- set system_message = messages[0]['content']|trim %}\n    {%- set messages = messages[1:] %}\n{%- else %}\n    {%- set system_message = \"\" %}\n{%- endif %}\n\n{#- System message #}\n{{- \"<|start_header_id|>system<|end_header_id|>\\n\\n\" }}\n{%- if tools is not none %}\n    {{- \"Environment: ipython\\n\" }}\n{%- endif %}\n{{- \"Cutting Knowledge Date: December 2023\\n\" }}\n{{- \"Today Date: \" + date_string + \"\\n\\n\" }}\n{%- if tools is not none and not tools_in_user_message %}\n    {{- \"You have access to the following functions. To call a function, please respond with JSON for a function call.\" }}\n    {{- 'Respond in the format {\"name\": function name, \"parameters\": dictionary of argument name and its value}.' }}\n    {{- \"Do not use variables.\\n\\n\" }}\n    {%- for t in tools %}\n        {{- t | tojson(indent=4) }}\n        {{- \"\\n\\n\" }}\n    {%- endfor %}\n{%- endif %}\n{{- system_message }}\n{{- \"<|eot_id|>\" }}\n\n{#- Custom tools are passed in a user message with some extra guidance #}\n{%- if tools_in_user_message and not tools is none %}\n    {#- Extract the first user message so we can plug it in here #}\n    {%- if messages | length != 0 %}\n        {%- set first_user_message = messages[0]['content']|trim %}\n        {%- set messages = messages[1:] %}\n    {%- else %}\n        {{- raise_exception(\"Cannot put tools in the first user message when there's no first user message!\") }}\n{%- endif %}\n    {{- '<|start_header_id|>user<|end_header_id|>\\n\\n' -}}\n    {{- \"Given the following functions, please respond with a JSON for a function call \" }}\n    {{- \"with its proper arguments that best answers the given prompt.\\n\\n\" }}\n    {{- 'Respond in the format {\"name\": function name, \"parameters\": dictionary of argument name and its value}.' }}\n    {{- \"Do not use variables.\\n\\n\" }}\n    {%- for t in tools %}\n        {{- t | tojson(indent=4) }}\n        {{- \"\\n\\n\" }}\n    {%- endfor %}\n    {{- first_user_message + \"<|eot_id|>\"}}\n{%- endif %}\n\n{%- for message in messages %}\n    {%- if not (message.role == 'ipython' or message.role == 'tool' or 'tool_calls' in message) %}\n        {{- '<|start_header_id|>' + message['role'] + '<|end_header_id|>\\n\\n'+ message['content'] | trim + '<|eot_id|>' }}\n    {%- elif 'tool_calls' in message %}\n        {%- if not message.tool_calls|length == 1 %}\n            {{- raise_exception(\"This model only supports single tool-calls at once!\") }}\n        {%- endif %}\n        {%- set tool_call = message.tool_calls[0].function %}\n        {{- '<|start_header_id|>assistant<|end_header_id|>\\n\\n' -}}\n        {{- '{\"name\": \"' + tool_call.name + '\", ' }}\n        {{- '\"parameters\": ' }}\n        {{- tool_call.arguments | tojson }}\n        {{- \"}\" }}\n        {{- \"<|eot_id|>\" }}\n    {%- elif message.role == \"tool\" or message.role == \"ipython\" %}\n        {{- \"<|start_header_id|>ipython<|end_header_id|>\\n\\n\" }}\n        {%- if message.content is mapping or message.content is iterable %}\n            {{- message.content | tojson }}\n        {%- else %}\n            {{- message.content }}\n        {%- endif %}\n        {{- \"<|eot_id|>\" }}\n    {%- endif %}\n{%- endfor %}\n{%- if add_generation_prompt %}\n    {{- '<|start_header_id|>assistant<|end_header_id|>\\n\\n' }}\n{%- endif %}\n",
```
3. Save and exit.
     
If you'd like to know more about the above error, here's the exact error message: "ValueError: Cannot use chat template functions because tokenizer.chat_template is not set and no template argument was passed!" and a [brief discussion](https://discuss.huggingface.co/t/chat-template-is-not-set-throwing-error/104095) about it on the Hugging Face website.
   
### 2.2 Via HuggingFace (account required)
  
```
pip install huggingface-hub
```
   
The first list below is adapted from [meta-llama](https://github.com/meta-llama/llama-models?tab=readme-ov-file#download) Github.
   
1. Create a [Hugging Face account](https://huggingface.co/). 
2. Visit the [Llama3.2-3B-Instruct repository](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).
3. Read and accept the license. Once your request is approved, you'll be granted access to all Llama 3.2 models. Note that requests used to take up to one hour to get processed.
4. Create an access token to use the models you have been granted access to:
   - Click on your profile
   - Click on "Access Tokens"
   - Click on "Create new token" in the top right-hand corner
   - Choose "Read" for "Token type" at the top, give the token a name, save the token value
5. In the terminal, run `hugginface-cli login`.
6. Pass the access token created.   
  
You'll need to do steps 5 and 6 every time you start a new terminal.

### 2.3 Example
  
Check that everything is set up correctly.  
  
The following code should now work:    
Replace  **PATH** by **PATH3** if you have followed the instructions in section 2.1, and by `meta-llama/Llama-3.2-3B-Instruct` if you have followed the instructions in section 2.2.
```
import torch
from transformers import pipeline

model_id = "PATH"
pipe = pipeline(
    "text-generation",
    model=model_id,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
messages = [
    {"role": "system", "content": "You are a pirate chatbot who always responds in pirate speak!"},
    {"role": "user", "content": "Who are you?"},
]
outputs = pipe(
    messages,
    max_new_tokens=256,
)
print(outputs[0]["generated_text"][-1])
```
  
If you want to avoid the "Setting `pad_token_id` to `eos_token_id`:None for open-end generation." warning message, add `pad_token_id=pipe.tokenizer.eos_token_id` to `outputs` after `max_new_tokens=256`. This [article](https://jaketae.github.io/study/gpt2/#setup) explains what's behind the warning.

## 3. Instructions