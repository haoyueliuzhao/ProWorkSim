"""Use the original raw-owner CLI with precise formal budget-boundary RPC closure."""
from proworksim import software_benchmark_owner_ipc_v054 as original
from proworksim.software_benchmark_normal_boundary_v054 import FormalOwnerService


if __name__ == "__main__":
    # Service protocol specialization only: CalibrationActor, load_actor,
    # complete/generate_native, cache context and numerical contract are untouched.
    original.OwnerService = FormalOwnerService
    original.main()
