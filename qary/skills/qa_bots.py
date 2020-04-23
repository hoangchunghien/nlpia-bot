""" Transformer based chatbot dialog engine for answering questions """

import logging
import os
import urllib.request
import uuid
import zipfile
from multiprocessing import cpu_count

from qary.skills.qa_models import QuestionAnsweringModel
from qary.constants import DATA_DIR, USE_CUDA, args
from qary.skills.basebots import ContextBot
from qary.etl.netutils import DownloadProgressBar
from qary.etl import scrape_wikipedia


log = logging.getLogger(__name__)


class Bot(ContextBot):
    """ Bot that provides answers to questions given context data containing the answer """

    def __init__(self, context=None, args=args, **kwargs):
        super().__init__(context=context, args=args, **kwargs)
        self.transformer_loggers = []
        for name in logging.root.manager.loggerDict:
            if (len(name) >= 12 and name[:12] == 'transformers') or name == 'qary.skills.qa_utils':
                self.transformer_loggers.append(logging.getLogger(name))
                self.transformer_loggers[-1].setLevel(logging.ERROR)

        qa_model = args.qa_model
        url_str = f"http://totalgood.org/midata/models/qa/{qa_model}.zip"
        model_dir = os.path.join(DATA_DIR, 'qa-models', f"{qa_model}")
        model_type = qa_model.split('-')[0].lower()
        if not os.path.isdir(model_dir):
            os.makedirs(model_dir)

        if (
            not os.path.exists(os.path.join(model_dir, 'config.json')) or
            not os.path.exists(os.path.join(model_dir, 'pytorch_model.bin')) or
            not os.path.exists(os.path.join(model_dir, 'tokenizer_config.json')) or
            not os.path.exists(os.path.join(model_dir, 'version.json')) or
            (model_type == 'bert' and not os.path.exists(os.path.join(model_dir, 'vocab.txt'))) or
            (model_type == 'albert' and not os.path.exists(os.path.join(model_dir, 'spiece.model')))
        ):
            zip_local_path = os.path.join(DATA_DIR, 'qa-models', f"{qa_model}.zip")
            with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=url_str.split('/')[-1]) as t:
                urllib.request.urlretrieve(url_str, filename=zip_local_path, reporthook=t.update_to)
            with zipfile.ZipFile(zip_local_path, 'r') as zip_file:
                zip_file.extractall(os.path.join(DATA_DIR, 'qa-models'))
            os.remove(zip_local_path)

        model_args = {
            'process_count': cpu_count() - 2 if cpu_count() > 2 else 1,
            'output_dir': model_dir,
            'cache_dir': model_dir,
            'no_cache': True,
            'use_cached_eval_features': False,
            'overwrite_output_dir': False,
            'silent': True
        }

        self.model = QuestionAnsweringModel(
            model_type, model_dir, args=model_args, pretrained=True, use_cuda=USE_CUDA
        )

    def encode_input(self, statement, text):
        """ Converts statement and context strings into json format compatible with BERT transformer

        BERT models use the word "context" to mean a single document read by BERT to do QA.
        qary.skills.basebots uses context to manage a dict of many variables that help manage convo.

        >>> bot = Bot()
        >>> encoded = bot.encode_input('statement', text='example text')
        >>> encoded[0]['qas'][0]['question']
        'statement'
        >>> encoded[0]['context']
        'example text'
        """
        encoded = [{
            'qas': [{
                'id': str(uuid.uuid1()),
                'question': statement
            }],
            'context': text
        }]
        return encoded

    def decode_output(self, output):
        """
        Extracts reply string from the model's prediction output

        >>> bot = Bot()
        >>> bot.decode_output([{'id': 'unique_id', 'answer': 'response', 'probability': 0.75}])
        (0.75, 'response')
        """
        return output[0]['probability'], output[0]['answer']

    def reply(self, statement, context=None, **kwargs):
        responses = super().reply(statement=statement, context=context, **kwargs) or []
        docs = self.context['doc']['text']
        if docs:
            docs = [docs]
        else:
            docs = scrape_wikipedia.find_article_texts(query=statement, max_articles=1, max_depth=1, ngrams=3,
                                                       ignore='who what when where why'.split())
        if len(docs):
            for text in docs:
                encoded_input = self.encode_input(statement, text)
                encoded_output = self.model.predict(encoded_input)
                probability, response = self.decode_output(encoded_output)
                if len(response) > 0:
                    responses.append((probability, response))
        return responses


if __name__ == '__main__':
    bot = Bot()
