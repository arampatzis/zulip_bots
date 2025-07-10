## 🚀 Running the Zulip ChatGPT Bot with Docker

### 1. **Build the Docker Image**
```bash
docker build -t kita-bot .
```

### 2. **Prepare your `.env` File**

Create a `.env` file in your project root with:
```
OPENAI_API_KEY=your-openai-key
```

### 3. **Run the Bot (Standard Mode)**
```bash
docker run --env-file .env kita-bot
```

### 4. **(Recommended for Development) Live Code Reload**

Mount your local code into the container for instant changes:
```bash
docker run --rm --env-file .env -v $(pwd):/app kita-bot poetry run kita
```

### 5. **(Optional) Start a Shell in the Container**

For debugging, start an interactive bash shell:
```bash
docker run -it --env-file .env -v $(pwd):/app kita-bot /bin/bash
```
Then inside the container, run:
```bash
poetry run kita
```
or
```bash
poetry run python bots/kita.py
```

## Developing with Docker

First, build and run the docker container using `just`:
```bash
just build-docker
just run-docker
```

Inside the container, run:
```bash
poetry shell
```
to create the environment and open a shell with the environment activated.

Open `Cursor` and press `Ctrl+Shift+P` or `Cmd+Shift+P` to open the command palette.
Then type `Remote-Containers: Open Folder in Container` and select the project root.
