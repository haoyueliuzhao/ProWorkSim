"""One actual SDK schema serialization control; zero completions or processes."""
import copy
import os
import sys
import unittest

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1',
                  HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')


def deny(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto', 'subprocess.Popen'}:
        raise AssertionError('This schema control cannot use network, models or child processes')


sys.addaudithook(deny)

from openhands.sdk import Action  # noqa: E402
from proworksim import software_benchmark_tooling_v120 as old  # noqa: E402
from proworksim import software_benchmark_tooling_v130 as new  # noqa: E402


class SDKDeclarationControl(unittest.TestCase):
    def test_actual_sdk_conversion_changes_only_read_path_description(self):
        before = old.tool_definitions(new.schema_inventory_case())
        after = new.tool_definitions(new.schema_inventory_case())
        self.assertEqual([item['name'] for item in before], [item['name'] for item in after])
        for index, (prior, current) in enumerate(zip(before, after)):
            # Same class name removes meaningless generated title differences.
            prior_type = Action.from_mcp_schema(f'Schema130_{index}', prior['parameters'])
            current_type = Action.from_mcp_schema(f'Schema130_{index}', current['parameters'])
            expected = copy.deepcopy(prior_type.model_json_schema())
            if current['name'] == 'read_file':
                expected['properties']['path']['description'] = new.PATH_DESCRIPTION
                value = current_type.model_validate({'path': 'sample.py', 'cursor': None})
                self.assertEqual(value.model_dump(exclude_unset=True, exclude_computed_fields=True),
                                 {'path': 'sample.py', 'cursor': None})
            self.assertEqual(current_type.model_json_schema(), expected)
        self.assertIs(new.ToolFeedbackWorkerMixin, old.ToolFeedbackWorkerMixin)


if __name__ == '__main__':
    unittest.main(verbosity=2)
