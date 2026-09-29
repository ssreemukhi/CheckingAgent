import json
from pathlib import Path

out_dir = Path("test_cases")
out_dir.mkdir(exist_ok=True)

cases = [
{
  "case_id": "001",
  "description": "Quote vs Policy - deductible mismatch and missing waiver of subrogation",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Ashford Retail Holdings LLC\nEffective Date: 08/01/2026\nExpiration Date: 08/01/2027\nAnnual Premium: $18,450\nBuilding Limit: $2,500,000\nBusiness Personal Property Limit: $500,000\nDeductible: $10,000\nCoinsurance: 90%\nWaiver of Subrogation: Included",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Ashford Retail Holdings LLC\nEffective Date: 08/01/2026\nExpiration Date: 08/01/2027\nAnnual Premium: $18,450\nBuilding Limit: $2,500,000\nBusiness Personal Property Limit: $500,000\nDeductible: $25,000\nCoinsurance: 90%\nWaiver of Subrogation: Not included",
  "fields": ["Named insured","Effective date","Annual premium","Building limit","Business personal property limit","Deductible","Coinsurance","Waiver of subrogation"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Effective date","status":"matched"},
    {"field":"Annual premium","status":"matched"},{"field":"Building limit","status":"matched"},
    {"field":"Business personal property limit","status":"matched"},{"field":"Deductible","status":"flagged"},
    {"field":"Coinsurance","status":"matched"},{"field":"Waiver of subrogation","status":"flagged"}]
},
{
  "case_id": "002",
  "description": "Quote vs Policy - clean match, no discrepancies (control case)",
  "source_text": "QUOTE - Commercial General Liability\nNamed Insured: Meridian Foods Pvt Ltd\nEffective Date: 09/15/2026\nAnnual Premium: Rs 1,24,000\nEach Occurrence Limit: Rs 50,00,000\nGeneral Aggregate Limit: Rs 1,00,00,000\nDeductible: Rs 25,000\nAdditional Insured: Landlord - Skyline Properties",
  "target_text": "POLICY - Commercial General Liability\nNamed Insured: Meridian Foods Pvt Ltd\nEffective Date: 09/15/2026\nAnnual Premium: Rs 1,24,000\nEach Occurrence Limit: Rs 50,00,000\nGeneral Aggregate Limit: Rs 1,00,00,000\nDeductible: Rs 25,000\nAdditional Insured: Landlord - Skyline Properties",
  "fields": ["Named insured","Effective date","Annual premium","Each occurrence limit","General aggregate limit","Deductible","Additional insured"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Effective date","status":"matched"},
    {"field":"Annual premium","status":"matched"},{"field":"Each occurrence limit","status":"matched"},
    {"field":"General aggregate limit","status":"matched"},{"field":"Deductible","status":"matched"},
    {"field":"Additional insured","status":"matched"}]
},
{
  "case_id": "003",
  "description": "Binder vs Policy - named insured spelling mismatch and missing endorsement form",
  "source_text": "BINDER - Commercial Auto\nNamed Insured: Vantage Logistics Pvt. Ltd.\nEffective Date: 07/01/2026\nAnnual Premium: Rs 3,45,000\nLiability Limit: Rs 75,00,000\nUninsured Motorist Coverage: Included\nEndorsement Forms: CA 20 48 - Waiver of Subrogation, CA 99 54 - Notice of Cancellation",
  "target_text": "POLICY - Commercial Auto\nNamed Insured: Vantage Logisitcs Pvt. Ltd.\nEffective Date: 07/01/2026\nAnnual Premium: Rs 3,45,000\nLiability Limit: Rs 75,00,000\nUninsured Motorist Coverage: Included\nEndorsement Forms: CA 20 48 - Waiver of Subrogation",
  "fields": ["Named insured","Effective date","Annual premium","Liability limit","Uninsured motorist coverage","Endorsement forms"],
  "ground_truth": [
    {"field":"Named insured","status":"flagged"},{"field":"Effective date","status":"matched"},
    {"field":"Annual premium","status":"matched"},{"field":"Liability limit","status":"matched"},
    {"field":"Uninsured motorist coverage","status":"matched"},{"field":"Endorsement forms","status":"flagged"}]
},
{
  "case_id": "004",
  "description": "Endorsement request vs issued Policy - missing additional insured and effective date mismatch",
  "source_text": "ENDORSEMENT REQUEST - Add Additional Insured\nNamed Insured: Crestpoint Manufacturing Ltd\nEffective Date: 03/10/2026\nAdditional Insured Requested: Northbridge Capital Partners\nCoverage Line: Commercial Property",
  "target_text": "POLICY ENDORSEMENT - Issued\nNamed Insured: Crestpoint Manufacturing Ltd\nEffective Date: 03/15/2026\nAdditional Insured Added: None\nCoverage Line: Commercial Property",
  "fields": ["Named insured","Effective date","Additional insured","Coverage line"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Effective date","status":"flagged"},
    {"field":"Additional insured","status":"flagged"},{"field":"Coverage line","status":"matched"}]
},
{
  "case_id": "005",
  "description": "Policy vs Renewal - reduced BPP limit and dropped waiver of subrogation",
  "source_text": "POLICY (Prior term) - Commercial Property\nNamed Insured: Solace Wellness Studios LLP\nAnnual Premium: Rs 2,10,000\nBuilding Limit: Rs 1,80,00,000\nBusiness Personal Property Limit: Rs 40,00,000\nDeductible: Rs 50,000\nWaiver of Subrogation: Included",
  "target_text": "RENEWAL POLICY - Commercial Property\nNamed Insured: Solace Wellness Studios LLP\nAnnual Premium: Rs 2,10,000\nBuilding Limit: Rs 1,80,00,000\nBusiness Personal Property Limit: Rs 25,00,000\nDeductible: Rs 50,000\nWaiver of Subrogation: Not included",
  "fields": ["Named insured","Annual premium","Building limit","Business personal property limit","Deductible","Waiver of subrogation"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Building limit","status":"matched"},{"field":"Business personal property limit","status":"flagged"},
    {"field":"Deductible","status":"matched"},{"field":"Waiver of subrogation","status":"flagged"}]
},
{
  "case_id": "006",
  "description": "Quote vs Policy - premium entered incorrectly",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Brightline Textiles Pvt Ltd\nEffective Date: 09/01/2026\nAnnual Premium: Rs 2,85,000\nBuilding Limit: Rs 3,20,00,000\nDeductible: Rs 75,000",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Brightline Textiles Pvt Ltd\nEffective Date: 09/01/2026\nAnnual Premium: Rs 2,58,000\nBuilding Limit: Rs 3,20,00,000\nDeductible: Rs 75,000",
  "fields": ["Named insured","Effective date","Annual premium","Building limit","Deductible"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Effective date","status":"matched"},
    {"field":"Annual premium","status":"flagged"},{"field":"Building limit","status":"matched"},
    {"field":"Deductible","status":"matched"}]
},
{
  "case_id": "007",
  "description": "Policy vs Renewal - clean match, no discrepancies",
  "source_text": "POLICY (Prior term) - Workers Compensation\nNamed Insured: Orbit Facility Services LLP\nAnnual Premium: Rs 4,10,000\nEmployers Liability Limit: Rs 1,00,00,000\nExperience Modifier: 0.94",
  "target_text": "RENEWAL POLICY - Workers Compensation\nNamed Insured: Orbit Facility Services LLP\nAnnual Premium: Rs 4,10,000\nEmployers Liability Limit: Rs 1,00,00,000\nExperience Modifier: 0.94",
  "fields": ["Named insured","Annual premium","Employers liability limit","Experience modifier"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Employers liability limit","status":"matched"},{"field":"Experience modifier","status":"matched"}]
},
{
  "case_id": "008",
  "description": "Quote vs Policy - flood exclusion silently added",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Harborview Cold Storage Ltd\nAnnual Premium: Rs 6,20,000\nBuilding Limit: Rs 8,50,00,000\nExclusions: None specified beyond standard form",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Harborview Cold Storage Ltd\nAnnual Premium: Rs 6,20,000\nBuilding Limit: Rs 8,50,00,000\nExclusions: Flood damage excluded (Endorsement CP 10 65)",
  "fields": ["Named insured","Annual premium","Building limit","Exclusions"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Building limit","status":"matched"},{"field":"Exclusions","status":"flagged"}]
},
{
  "case_id": "009",
  "description": "Binder vs Policy - clean match",
  "source_text": "BINDER - Directors and Officers Liability\nNamed Insured: Northfield Analytics Inc\nAnnual Premium: $22,000\nLimit of Liability: $5,000,000\nRetention: $50,000",
  "target_text": "POLICY - Directors and Officers Liability\nNamed Insured: Northfield Analytics Inc\nAnnual Premium: $22,000\nLimit of Liability: $5,000,000\nRetention: $50,000",
  "fields": ["Named insured","Annual premium","Limit of liability","Retention"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Limit of liability","status":"matched"},{"field":"Retention","status":"matched"}]
},
{
  "case_id": "010",
  "description": "Quote vs Policy - coinsurance percentage changed",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Alderwood Packaging Co\nAnnual Premium: Rs 3,95,000\nBuilding Limit: Rs 4,00,00,000\nCoinsurance: 80%",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Alderwood Packaging Co\nAnnual Premium: Rs 3,95,000\nBuilding Limit: Rs 4,00,00,000\nCoinsurance: 90%",
  "fields": ["Named insured","Annual premium","Building limit","Coinsurance"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Building limit","status":"matched"},{"field":"Coinsurance","status":"flagged"}]
},
{
  "case_id": "011",
  "description": "Policy vs Renewal - liability limit quietly reduced",
  "source_text": "POLICY (Prior term) - General Liability\nNamed Insured: Sundale Hospitality Group\nEach Occurrence Limit: Rs 1,00,00,000\nGeneral Aggregate: Rs 2,00,00,000",
  "target_text": "RENEWAL POLICY - General Liability\nNamed Insured: Sundale Hospitality Group\nEach Occurrence Limit: Rs 75,00,000\nGeneral Aggregate: Rs 2,00,00,000",
  "fields": ["Named insured","Each occurrence limit","General aggregate"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Each occurrence limit","status":"flagged"},
    {"field":"General aggregate","status":"matched"}]
},
{
  "case_id": "012",
  "description": "Quote vs Policy - clean match, umbrella policy",
  "source_text": "QUOTE - Commercial Umbrella\nNamed Insured: Prestige Auto Dealers Pvt Ltd\nAnnual Premium: Rs 5,40,000\nLimit: Rs 5,00,00,000\nUnderlying GL Required: Rs 1,00,00,000",
  "target_text": "POLICY - Commercial Umbrella\nNamed Insured: Prestige Auto Dealers Pvt Ltd\nAnnual Premium: Rs 5,40,000\nLimit: Rs 5,00,00,000\nUnderlying GL Required: Rs 1,00,00,000",
  "fields": ["Named insured","Annual premium","Limit","Underlying GL required"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Limit","status":"matched"},{"field":"Underlying GL required","status":"matched"}]
},
{
  "case_id": "013",
  "description": "Endorsement vs Policy - expiration date year typo",
  "source_text": "ENDORSEMENT - Extend Policy Term\nNamed Insured: Fairmount Logistics Hub\nEffective Date: 01/12/2026\nRevised Expiration Date: 01/12/2027",
  "target_text": "POLICY (Updated) - Extend Policy Term\nNamed Insured: Fairmount Logistics Hub\nEffective Date: 01/12/2026\nRevised Expiration Date: 01/12/2026",
  "fields": ["Named insured","Effective date","Revised expiration date"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Effective date","status":"matched"},
    {"field":"Revised expiration date","status":"flagged"}]
},
{
  "case_id": "014",
  "description": "Quote vs Policy - clean match, cyber liability",
  "source_text": "QUOTE - Cyber Liability\nNamed Insured: Vireo Health Tech Pvt Ltd\nAnnual Premium: Rs 4,75,000\nAggregate Limit: Rs 3,00,00,000\nRetention: Rs 5,00,000",
  "target_text": "POLICY - Cyber Liability\nNamed Insured: Vireo Health Tech Pvt Ltd\nAnnual Premium: Rs 4,75,000\nAggregate Limit: Rs 3,00,00,000\nRetention: Rs 5,00,000",
  "fields": ["Named insured","Annual premium","Aggregate limit","Retention"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Aggregate limit","status":"matched"},{"field":"Retention","status":"matched"}]
},
{
  "case_id": "015",
  "description": "Binder vs Policy - additional insured omitted at issuance",
  "source_text": "BINDER - Commercial Property\nNamed Insured: Ridgeline Warehousing Corp\nAdditional Insured: First Capital Bank (Mortgagee)\nAnnual Premium: Rs 7,10,000",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Ridgeline Warehousing Corp\nAdditional Insured: None listed\nAnnual Premium: Rs 7,10,000",
  "fields": ["Named insured","Additional insured","Annual premium"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Additional insured","status":"flagged"},
    {"field":"Annual premium","status":"matched"}]
},
{
  "case_id": "016",
  "description": "Quote vs Policy - clean match, marine cargo",
  "source_text": "QUOTE - Marine Cargo\nNamed Insured: Coastal Exports Ltd\nAnnual Premium: Rs 2,10,000\nLimit per Conveyance: Rs 1,50,00,000\nDeductible: Rs 25,000",
  "target_text": "POLICY - Marine Cargo\nNamed Insured: Coastal Exports Ltd\nAnnual Premium: Rs 2,10,000\nLimit per Conveyance: Rs 1,50,00,000\nDeductible: Rs 25,000",
  "fields": ["Named insured","Annual premium","Limit per conveyance","Deductible"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Limit per conveyance","status":"matched"},{"field":"Deductible","status":"matched"}]
},
{
  "case_id": "017",
  "description": "Policy vs Renewal - named insured entity name changed without proper endorsement",
  "source_text": "POLICY (Prior term) - Commercial Property\nNamed Insured: Kestrel Manufacturing Pvt Ltd\nAnnual Premium: Rs 3,60,000\nBuilding Limit: Rs 2,90,00,000",
  "target_text": "RENEWAL POLICY - Commercial Property\nNamed Insured: Kestrel Manufacturing and Allied Industries Pvt Ltd\nAnnual Premium: Rs 3,60,000\nBuilding Limit: Rs 2,90,00,000",
  "fields": ["Named insured","Annual premium","Building limit"],
  "ground_truth": [
    {"field":"Named insured","status":"flagged"},{"field":"Annual premium","status":"matched"},
    {"field":"Building limit","status":"matched"}]
},
{
  "case_id": "018",
  "description": "Quote vs Policy - compound error, both deductible and BPP limit wrong",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Silverline Electronics Pvt Ltd\nBuilding Limit: Rs 1,50,00,000\nBusiness Personal Property Limit: Rs 60,00,000\nDeductible: Rs 50,000",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Silverline Electronics Pvt Ltd\nBuilding Limit: Rs 1,50,00,000\nBusiness Personal Property Limit: Rs 45,00,000\nDeductible: Rs 1,00,000",
  "fields": ["Named insured","Building limit","Business personal property limit","Deductible"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Building limit","status":"matched"},
    {"field":"Business personal property limit","status":"flagged"},{"field":"Deductible","status":"flagged"}]
},
{
  "case_id": "019",
  "description": "Binder vs Policy - clean match, professional indemnity",
  "source_text": "BINDER - Professional Indemnity\nNamed Insured: Clearpath Consulting Group\nAnnual Premium: Rs 1,85,000\nLimit of Indemnity: Rs 2,00,00,000\nRetroactive Date: 04/01/2022",
  "target_text": "POLICY - Professional Indemnity\nNamed Insured: Clearpath Consulting Group\nAnnual Premium: Rs 1,85,000\nLimit of Indemnity: Rs 2,00,00,000\nRetroactive Date: 04/01/2022",
  "fields": ["Named insured","Annual premium","Limit of indemnity","Retroactive date"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Annual premium","status":"matched"},
    {"field":"Limit of indemnity","status":"matched"},{"field":"Retroactive date","status":"matched"}]
},
{
  "case_id": "020",
  "description": "Quote vs Policy - sublimit for water damage silently removed",
  "source_text": "QUOTE - Commercial Property\nNamed Insured: Meadowbrook Senior Living LLC\nBuilding Limit: Rs 5,00,00,000\nSublimit - Water Damage: Rs 25,00,000\nAnnual Premium: Rs 4,40,000",
  "target_text": "POLICY - Commercial Property\nNamed Insured: Meadowbrook Senior Living LLC\nBuilding Limit: Rs 5,00,00,000\nSublimit - Water Damage: Not listed\nAnnual Premium: Rs 4,40,000",
  "fields": ["Named insured","Building limit","Sublimit - Water Damage","Annual premium"],
  "ground_truth": [
    {"field":"Named insured","status":"matched"},{"field":"Building limit","status":"matched"},
    {"field":"Sublimit - Water Damage","status":"flagged"},{"field":"Annual premium","status":"matched"}]
}
]

for case in cases:
    path = out_dir / f"case_{case['case_id']}.json"
    with open(path, "w") as f:
        json.dump(case, f, indent=2)

print(f"Wrote {len(cases)} test cases to {out_dir}")
