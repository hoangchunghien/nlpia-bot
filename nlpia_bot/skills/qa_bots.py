""" Transformer based chatbot dialog engine for answering questions """

import os
import uuid

from simpletransformers.question_answering import QuestionAnsweringModel

from nlpia_bot.etl import scrape_wikipedia
from nlpia_bot.constants import DATA_DIR


class Bot:

    class NullWriter(object):
        def write(self, arg):
            pass

    def __init__(self, path=os.path.join(DATA_DIR, 'simple-transformer')):
        self.model = QuestionAnsweringModel('bert', path, use_cuda=True)

    def encode_input(self, statement, context):
        encoded = [{
            'qas': [{
                'id': str(uuid.uuid1()),
                'question': statement
            }],
            'context': context
        }]
        return encoded

    def decode_output(self, output):
        return output[0]['answer']

    def reply(self, statement):
        response = ''
        docs = scrape_wikipedia.scrape_article_texts()
        for context in docs:
            encoded_input = self.encode_input(statement, context)
            encoded_output = self.model.predict(encoded_input)
            decoded_output = self.decode_output(encoded_output)
            if len(decoded_output) > 0:
                response = response + decoded_output + ' . . .\n'
        score = 1 if len(response) > 0 else 0
        return [(score, response.rstrip())]


def main():
    pass


if __name__ == '__main__':
    main()
