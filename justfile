default:
  @just --list

alias build := build-image
alias run := run-container
alias start := start-container
alias stop := stop-container
alias rm := remove-container

build-image:
    docker build -t kita-bot .

run-container:
    docker run --hostname bots -d --env-file .env -v $(pwd):/app --name kita-bot-dev kita-bot

start-container:
  docker exec -it kita-bot-dev /bin/bash

stop-container:
  docker stop kita-bot-dev

remove-container:
  docker rm kita-bot-dev




