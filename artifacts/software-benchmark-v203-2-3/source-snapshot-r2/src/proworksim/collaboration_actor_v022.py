"""One shared existing actor/optimizer with the frozen N1 learner function."""
from .candidate_runtime_v0201 import CandidateActor
from .functional_qwen_v022 import learning_logprobs


class FunctionalCandidateActor(CandidateActor):
    def learning_logprobs(self, trace):
        self._verify_execution()
        result = learning_logprobs(self.model, trace)
        if result.dtype != self.torch.float32:
            raise ValueError('Functional learner selected probabilities must remain FP32')
        return result
