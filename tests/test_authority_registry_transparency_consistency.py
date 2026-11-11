import hashlib
import json
from pathlib import Path

from agnxiv.authority import (
    RegistryCheckpointTransparencyConsistencyWitness,
    verify_registry_checkpoint_transparency_consistency,
)

ROOT = Path(__file__).resolve().parents[1]


def test_transparency_consistency_matrix_is_fail_closed():
    summary = json.loads(
        (ROOT / "research/results/authority-registry-transparency-consistency-summary.json").read_text()
    )
    audit = json.loads(
        (ROOT / "research/results/authority-registry-transparency-consistency-audit.json").read_text()
    )
    assert summary["checkpoint_only_false_passes"] == 128
    assert summary["consistency_verified_false_passes"] == 0
    assert summary["consistency_verified_controls_passed"] == 32
    assert all(value == 32 for value in summary["families_blocked"].values())
    assert all(summary["negative_controls"].values())
    assert audit["production_imports"] == 0
    assert audit["independently_verified_attacks"] == 0
    assert audit["independently_verified_controls"] == 32
    assert audit["passed"] is True


def test_consistency_verifier_matches_reference_proofs_across_tree_sizes():
    def leaf(value):
        return hashlib.sha256(b"\x00" + value).digest()

    def node(left, right):
        return hashlib.sha256(b"\x01" + left + right).digest()

    def tree_hash(values):
        if len(values) == 1:
            return leaf(values[0])
        split = 1 << (len(values) - 1).bit_length() - 1
        if split == len(values):
            split //= 2
        return node(tree_hash(values[:split]), tree_hash(values[split:]))

    def subproof(old_size, values, complete):
        if old_size == len(values):
            return [] if complete else [tree_hash(values)]
        split = 1 << (len(values) - 1).bit_length() - 1
        if split == len(values):
            split //= 2
        if old_size <= split:
            return subproof(old_size, values[:split], complete) + [
                tree_hash(values[split:])
            ]
        return subproof(old_size - split, values[split:], False) + [
            tree_hash(values[:split])
        ]

    for new_size in range(2, 17):
        values = [index.to_bytes(2, "big") for index in range(new_size)]
        for old_size in range(1, new_size):
            proof = subproof(old_size, values, True)
            witness = RegistryCheckpointTransparencyConsistencyWitness(
                log_id="property-test",
                old_tree_size=old_size,
                old_root_sha256=tree_hash(values[:old_size]).hex(),
                new_tree_size=new_size,
                new_root_sha256=tree_hash(values).hex(),
                audit_path_sha256=[value.hex() for value in proof],
            )
            assert verify_registry_checkpoint_transparency_consistency(witness)
            corrupted = witness.model_copy(
                update={"new_root_sha256": "f" * 64}
            )
            assert not verify_registry_checkpoint_transparency_consistency(corrupted)
