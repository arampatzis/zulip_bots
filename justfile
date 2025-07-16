default:
  @just --list

build mode:
    @if [ "{{mode}}" = "dev" ] || [ "{{mode}}" = "deploy" ]; then \
        docker build --target {{mode}} -t bots:{{mode}} . ;\
    else \
        echo "Invalid mode: {{mode}}" ;\
        echo "Valid modes: dev, deploy" ;\
    fi

run mode:
    @if [ "{{mode}}" = "dev" ]; then \
        docker run -d \
            --hostname bots.dev \
            --env-file .env \
            -v $(pwd):/app \
            --name bots.dev \
            bots:dev; \
    elif [ "{{mode}}" = "kita" ] || [ "{{mode}}" = "arxiv" ]; then \
        docker run -d \
            --hostname bots.{{mode}} \
            --env-file .env \
            -v zulip-bot-data:/app/data \
            --name bots.app \
            bots:deploy \
            poetry run {{mode}}; \
    else \
        echo "Invalid mode: {{mode}}"; \
        echo "Valid modes: dev, kita, arxiv"; \
    fi

shell mode:
    @docker exec -it bots.{{mode}} /bin/bash

stop mode:
    @docker stop bots.{{mode}}

rm mode:
    @docker rm bots.{{mode}} || true

logs mode:
    @docker logs -f bots.{{mode}}

volume:
    @docker volume create zulip-bot-data
