import numpy as np


def test_coreml_text_embeddings_are_submitted_one_at_a_time(monkeypatch):
    import tasks.clap_analyzer as clap

    class FakeTokenizer:
        def __call__(self, texts, **kwargs):
            count = len(texts)
            return {
                'input_ids': np.zeros((count, 77), dtype=np.int64),
                'attention_mask': np.ones((count, 77), dtype=np.int64),
            }

    class FakeSession:
        def __init__(self):
            self.batch_sizes = []

        def get_providers(self):
            return ['CoreMLExecutionProvider', 'CPUExecutionProvider']

        def run(self, output_names, feeds):
            batch_size = feeds['input_ids'].shape[0]
            self.batch_sizes.append(batch_size)
            if batch_size != 1:
                raise AssertionError('CoreML CLAP text must receive batch size 1')
            return [np.ones((batch_size, 512), dtype=np.float32)]

    session = FakeSession()
    monkeypatch.setattr(clap.config, 'CLAP_ENABLED', True)
    monkeypatch.setattr(clap.config, 'CLAP_TEXT_COREML_ENABLED', True)
    monkeypatch.setattr(clap, 'get_clap_text_model', lambda: session)
    monkeypatch.setattr(clap, 'get_tokenizer', lambda: FakeTokenizer())

    result = clap.get_text_embeddings_batch(['danceable', 'aggressive', 'happy'])

    assert result.shape == (3, 512)
    assert session.batch_sizes == [1, 1, 1]
