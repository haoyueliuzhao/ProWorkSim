"""Keep full independent observation evidence when solver headers are bounded."""
from .software_collaboration_runtime_observer_v172 import RuntimeObservationBridge as PreviousBridge
from .software_public_test_view_v193 import full_observer_result

class RuntimeObservationBridge(PreviousBridge):
    def observe_public_test(self,member,result):
        return super().observe_public_test(member,full_observer_result(self.runtime.prepared.world,member,result))
