import os
import json
import requests
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()
# Support both ONE_MIN_AI_API_KEY (preferred) and ONE_MIN_API_KEY (legacy)
API_KEY = os.environ.get("ONE_MIN_AI_API_KEY") or os.environ.get("ONE_MIN_API_KEY")

URL = "https://api.1min.ai/api/features"


def _build_fallback_strategy_notes(combined_data: dict) -> Dict[str, Any]:
    """
    Generate fallback strategy notes when API is unavailable.
    Returns structured data similar to what the AI would return.
    """
    metrics = combined_data.get("metrics", {})
    permit_categories = combined_data.get("permit_categories", {})
    construction_summary = combined_data.get("construction_summary", {})
    timeline_summary = combined_data.get("timeline_summary", {})
    team_network = combined_data.get("team_network", {})
    
    tactics: List[str] = []
    risks: List[str] = []
    insights: List[str] = []
    
    # Generate tactics based on data
    scope_level = permit_categories.get("scope_level", "UNKNOWN")
    if scope_level == "HEAVY":
        tactics.append("Major construction project - ground-up build or substantial addition")
    elif scope_level == "MEDIUM":
        tactics.append("Moderate scope - significant remodel or addition work")
    else:
        tactics.append("Light scope - cosmetic or minor permitted work")
    
    if permit_categories.get("has_adu"):
        tactics.append("Added ADU to maximize density and rental income potential")
    
    if permit_categories.get("has_new_structure"):
        tactics.append("New structure built - maximized FAR utilization")
    
    if construction_summary.get("is_new_construction"):
        tactics.append("Ground-up new construction on cleared lot")
    elif construction_summary.get("added_sf"):
        added_sf = construction_summary.get("added_sf", 0)
        tactics.append(f"Added {added_sf:,} SF to existing structure")
    
    if permit_categories.get("has_pool"):
        tactics.append("Pool added for market appeal in luxury segment")
    
    # Generate risks based on permit flags
    if permit_categories.get("has_grading_or_hillside"):
        risks.append("Hillside/grading permits indicate challenging site conditions")
    
    if permit_categories.get("has_methane"):
        risks.append("Methane mitigation required - additional construction complexity")
    
    if permit_categories.get("has_fire_sprinklers"):
        if permit_categories.get("removed_fire_sprinklers"):
            risks.append("Fire sprinkler system removed - may indicate permit strategy")
        else:
            risks.append("Fire sprinkler system required - adds to construction cost")
    
    permit_complexity = permit_categories.get("permit_complexity_score", "UNKNOWN")
    if permit_complexity == "HIGH":
        risks.append("High permit complexity - multiple supplements and specialty permits")
    
    if permit_categories.get("supplement_count", 0) >= 3:
        risks.append(f"Multiple permit supplements ({permit_categories.get('supplement_count')}) may indicate plan changes or issues")
    
    # Default risks if none detected
    if not risks:
        risks.append("Standard permitting process - no unusual complexities detected")
    
    # Generate insights
    roi_pct = metrics.get("roi_pct")
    hold_days = metrics.get("hold_days")
    
    if roi_pct is not None and roi_pct > 30:
        insights.append(f"Strong returns ({roi_pct:.1f}% ROI) in current market conditions")
    elif roi_pct is not None:
        insights.append(f"Moderate returns ({roi_pct:.1f}% ROI) for this scope of work")
    
    if hold_days:
        if hold_days <= 365:
            insights.append(f"Quick turnaround ({hold_days} days) suggests efficient execution")
        elif hold_days <= 548:
            insights.append(f"Standard timeline ({hold_days} days) for scope of work")
        else:
            insights.append(f"Extended hold period ({hold_days} days) may indicate permitting or market challenges")
    
    # Check for owner-builder
    gc = team_network.get("primary_gc", {})
    if gc and "owner" in (gc.get("name", "").lower()):
        insights.append("Owner-builder project - experienced developer self-performing")
    
    return {
        "tactics": tactics[:6] if tactics else ["No specific tactics identified from permit data"],
        "risks": risks[:3] if risks else ["No unusual risks detected"],
        "insights": insights[:2] if insights else ["Insufficient data for market insights"],
        "source": "fallback",
    }


def summarize_comp(combined_data: dict) -> Dict[str, Any]:
    """
    Generates structured strategy notes for a comp analysis.
    
    Returns a dictionary with:
    - tactics: 3-6 bullets explaining what they built and why
    - risks: 2-3 bullets on potential issues
    - insights: 1-2 bullets on learnings from this comp
    - source: "api" or "fallback"
    
    Falls back to template-based generation if API is unavailable.
    """
    # Check if API key is available
    if not API_KEY:
        return _build_fallback_strategy_notes(combined_data)

    # Convert JSON to readable text for the prompt
    input_json_text = json.dumps(combined_data, indent=2, default=str)

    prompt_text = f"""
You are a comp-intel analyst for a Los Angeles real estate developer.

Analyze the following property data and provide a structured analysis.

IMPORTANT: Return ONLY valid JSON with this exact structure:
{{
  "tactics": [
    "bullet 1 - what they built and why",
    "bullet 2 - strategy used",
    "bullet 3 - value-add approach"
  ],
  "risks": [
    "risk 1 - e.g. hillside complexity",
    "risk 2 - e.g. permit delays"
  ],
  "insights": [
    "insight 1 - what we learn from this comp"
  ]
}}

Guidelines for content:
- tactics: 3-6 bullets explaining construction strategy, permit approach, value-add methods
  Examples: "Garage moved to front to maximize rear yard", "ADU added for rental income",
  "NFPA-13D removed to simplify construction", "Aggressive permit strategy with early starts"
  
- risks: 2-3 bullets on challenges or red flags
  Examples: "Hillside location adds grading complexity", "Long driveway increases utility costs",
  "Methane zone requires mitigation", "Multiple supplements suggest plan changes"
  
- insights: 1-2 bullets on learnings from this comp pattern
  Examples: "Quick approval timeline achievable in this area", "Owner-builder approach viable for experienced developers"

DO NOT include any text outside the JSON object.
DO NOT include markdown formatting or code blocks.

PROPERTY DATA:
{input_json_text}

Return ONLY the JSON object.
"""

    payload = {
        "type": "CHAT_WITH_AI",
        "model": "gpt-4o-mini",
        "promptObject": {
            "prompt": prompt_text,
            "isMixed": False,
            "webSearch": False,
        },
    }

    headers = {"API-KEY": API_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(URL, headers=headers, data=json.dumps(payload), timeout=120)
        resp.raise_for_status()
        
        data = resp.json()
        result_text = (
            data.get("aiRecord", {})
            .get("aiRecordDetail", {})
            .get("resultObject", [None])[0]
        )
        
        if isinstance(result_text, str) and result_text.strip():
            # Try to parse as JSON
            try:
                # Clean up potential markdown formatting
                clean_text = result_text.strip()
                if clean_text.startswith("```"):
                    # Remove markdown code blocks
                    clean_text = clean_text.replace("```json", "").replace("```", "").strip()
                
                parsed = json.loads(clean_text)
                
                # Validate structure
                if isinstance(parsed, dict) and "tactics" in parsed:
                    parsed["source"] = "api"
                    return parsed
            except json.JSONDecodeError:
                pass
            
            # If JSON parsing failed, return as raw text with fallback structure
            return {
                "tactics": [result_text[:500] if len(result_text) > 500 else result_text],
                "risks": [],
                "insights": [],
                "source": "api_raw",
            }
        
        # Fallback if no valid response
        return _build_fallback_strategy_notes(combined_data)
        
    except requests.exceptions.RequestException as e:
        print(f"[WARN] AI summarizer API error: {e}")
        return _build_fallback_strategy_notes(combined_data)
    except Exception as e:
        print(f"[WARN] AI summarizer error: {e}")
        return _build_fallback_strategy_notes(combined_data)
