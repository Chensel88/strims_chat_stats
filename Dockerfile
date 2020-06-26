FROM python:rc-buster

ADD logger.py /
ADD requirements.txt /

RUN pip install -r requirements.txt

CMD [ "python", "logger.py" ]
