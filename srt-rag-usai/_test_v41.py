#!/usr/bin/env python3
"""Quick test of the v4.1 applicability prompt against a few sample texts."""
import os, sys
from bedrock_adapter import BedrockAdapter

samples = [
    ("Keysight Power Sensor",
     "Combined Synopsis/Solicitation for a Keysight power sensor, model N8488A. "
     "The Naval Research Laboratory intends to procure RF power sensors for test "
     "and measurement of microwave signals. NAICS 334515. Delivery to NRL."),
    ("Pressure Gage (physical commodity)",
     "Proposed procurement for NSN 6685 Pressure Gage, 8-1/2 inch dial. "
     "Mechanical pressure gauge, analog dial readout. Quantity 50 each."),
    ("IT Managed Services",
     "Request for Proposal for comprehensive IT managed services including help desk, "
     "network administration, cybersecurity, and cloud hosting for the agency's systems."),
]

client = BedrockAdapter()
print("=== v4.1 applicability prompt test ===\n")
for title, txt in samples:
    r = client.assess_508_applicability(txt)
    print(f"[{title}]")
    print(f"  applicable: {r.get('is_508_applicable')}")
    print(f"  confidence: {r.get('confidence_label')} ({r.get('confidence_score')})")
    print(f"  reasoning: {r.get('applicability_explanation')[:160]}")
    print(f"  ict_found: {r.get('key_eit_indicators')}")
    print(f"  prompt_version: {r.get('applicability_prompt_version')}")
    print()
