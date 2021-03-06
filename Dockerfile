FROM ubuntu:latest
MAINTAINER Decky
RUN apt-get update -y
RUN apt-get install -y python-pip python-dev build-essential
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
WORKDIR decky
CMD . venv/bin/activate && pip install . && export FLASK_APP=decky && flask run 
