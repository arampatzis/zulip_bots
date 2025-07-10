# Use a slim Python base image
FROM python:3.11-slim

# Set environment variables for Python and Poetry
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

# Install git (needed for clone)
RUN apt-get update && apt-get install -y git wget pipx curl


RUN curl -L https://github.com/casey/just/releases/download/1.41.0/just-1.41.0-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz && mkdir -p /root/.local/bin && mv just /root/.local/bin


# Clone your shell setup repo
RUN git clone --depth 1 https://github.com/arampatzis/shell.git /root/shell

# Run your install script (if interactive, adjust as needed)
WORKDIR /root/shell
RUN python3 /root/shell/install.py --components oh_my_bash dotfiles omb_config dot_config ripgrep

# Install Poetry
RUN pipx install poetry
RUN pipx inject poetry poetry-plugin-shell
RUN poetry config virtualenvs.in-project true

# Set workdir
WORKDIR /app

# For production
COPY . .
RUN poetry install --no-interaction --no-ansi
CMD ["poetry", "run", "kita"]

# For development
# RUN poetry install --no-interaction --no-ansi
# RUN poetry run python3 -m pretty_errors -s
# CMD ["tail", "-f", "/dev/null"]
