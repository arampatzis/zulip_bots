default:
  @just --list

build target:
    docker build --target {{target}} -t kita:{{target}} .

run target:
    if [ "{{target}}" = "dev" ]; then \
        docker run --hostname bots -d --env-file .env -v $(pwd):/app --name kita.{{target}} kita:{{target}}; \
    else \
        docker run --hostname bots -d --env-file .env --name kita.{{target}} kita:{{target}}; \
    fi

start target:
    docker exec -it kita.{{target}} /bin/bash

stop target:
    docker stop kita.{{target}}

rm target:
    docker rm kita.{{target}} || true

logs target:
    docker logs -f kita.{{target}}
