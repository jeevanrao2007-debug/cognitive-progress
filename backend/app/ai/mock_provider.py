import json
import hashlib
import math
import re


class DeterministicMockProvider:
    """Offline fallback for local development and tests; it is not an AI model."""

    provider_name = "deterministic_mock"
    model_name = "rule-based-v1"

    def extract_progress(self, prompt: str) -> str:
        raw_text = self._input_text(prompt)
        lowered = raw_text.lower().strip()
        if not lowered:
            return json.dumps({"observations": []})

        # Backward compatibility for single-observation unit tests
        if "welding started at 4 pm" in lowered and "28 august" in lowered:
            return json.dumps({"observations": [{
                "discipline": "Piping",
                "location": "Unit 3",
                "activity_description": "24 inch line erection",
                "status": "completed",
                "actual_start": None,
                "actual_end": "2026-08-28",
                "progress": 100.0,
                "additional_context": "Welding started at 16:00",
                "confidence": 0.72,
            }]})

        # Natural language multi-event extraction
        observations = []
        parsed_date = self._parse_extracted_date(raw_text)

        # Check for Piping Erection / Spool activity
        if "erection" in lowered or ("line" in lowered and ("install" in lowered or "placed" in lowered or "completed" in lowered)):
            is_start = ("start" in lowered or "started" in lowered or "commenced" in lowered) and not ("completed" in lowered or "finished" in lowered)
            status = "in_progress" if is_start else ("completed" if ("complete" in lowered or "completed" in lowered or "finished" in lowered) else "in_progress")
            progress = 100.0 if status == "completed" else (10.0 if is_start else float(self._percentage(lowered, 50)))
            loc = "Unit 3" if "unit 3" in lowered else ("Unit 1" if "unit 1" in lowered else None)
            contractor = "Piping crew" if "piping crew" in lowered else None
            tag = "Line 24-XX" if ("24" in lowered or "line 24" in lowered) else None
            date_match = re.search(r"\b(202\d-\d{2}-\d{2})\b", raw_text)
            actual_end = date_match.group(1) if (date_match and status == "completed") else (parsed_date if (status == "completed" and not is_start) else None)
            actual_start = parsed_date if is_start else None
            time_match = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b", raw_text, re.IGNORECASE)
            time_note = f"Reported time: {time_match.group(1)}" if time_match else None
            observations.append({
                "discipline": "Piping",
                "location": loc,
                "activity_description": "24 inch line erection" if tag else "Piping spool erection",
                "status": status,
                "actual_start": actual_start,
                "actual_end": actual_end,
                "progress": progress,
                "contractor": contractor,
                "equipment_or_tag": tag,
                "additional_context": time_note,
                "notes": time_note,
                "source_span": "erection of the 24-inch line in Unit 3" if "unit 3" in lowered else None,
                "confidence": 0.94,
            })

        # Check for Valve installation / assembly
        if "valve" in lowered:
            is_start = ("start" in lowered or "started" in lowered or "commenced" in lowered) and not ("completed" in lowered or "finished" in lowered or "installed" in lowered)
            status = "in_progress" if is_start else ("completed" if ("installed" in lowered or "completed" in lowered or "finished" in lowered or "bolt-up" in lowered) else "in_progress")
            progress = 100.0 if status == "completed" else (10.0 if is_start else 50.0)
            loc = "Unit 3" if "unit 3" in lowered else None
            contractor = "Piping crew" if ("piping" in lowered or "piping crew" in lowered) else None
            tag = "XV-203" if "xv-203" in lowered else "Valve assembly"
            desc = "Installed valve XV-203 and completed bolt-up" if "xv-203" in lowered else "Valve installation"
            actual_start = parsed_date if is_start else None
            actual_end = parsed_date if status == "completed" else None
            observations.append({
                "discipline": "Piping",
                "location": loc,
                "activity_description": desc,
                "status": status,
                "actual_start": actual_start,
                "actual_end": actual_end,
                "progress": progress,
                "contractor": contractor,
                "equipment_or_tag": tag,
                "confidence": 0.93,
            })

        # Check for Hydrotest activity
        if "hydrotest" in lowered:
            is_completed = "hydrotest complete" in lowered or "hydrotest completed" in lowered or "hydrotest finished" in lowered
            status = "completed" if is_completed else "in_progress"
            progress = 100.0 if status == "completed" else 15.0
            loc = "Unit 3" if "unit 3" in lowered else None
            tag = "Line 18-AA" if "18" in lowered else ("Line 24-XX" if "24" in lowered else None)
            actual_start = parsed_date if ("start" in lowered or "prep" in lowered) else None
            actual_end = parsed_date if is_completed else None
            observations.append({
                "discipline": "Piping",
                "location": loc,
                "activity_description": "Hydrotest Line 18-AA" if "18" in lowered else "Hydrotest preparation",
                "status": status,
                "actual_start": actual_start,
                "actual_end": actual_end,
                "progress": progress,
                "contractor": "Testing crew" if "testing crew" in lowered else None,
                "equipment_or_tag": tag,
                "additional_context": "Hydrotest preparation commenced",
                "source_span": "Hydrotest preparation has started" if "preparation" in lowered else "Hydrotest activity",
                "confidence": 0.89,
            })

        # Check for Civil / Foundation / Excavation
        if "excavation" in lowered or "foundation" in lowered or "concrete" in lowered:
            status = "completed" if ("complete" in lowered or "completed" in lowered or "finished" in lowered) else "in_progress"
            progress = 100.0 if status == "completed" else float(self._percentage(lowered, 40))
            loc = "Unit 1" if "unit 1" in lowered else ("East Foundation" if "east" in lowered else None)
            desc = "Foundation excavation" if "excavation" in lowered else ("Concrete pour Unit 1" if "concrete" in lowered else "Civil foundation works")
            observations.append({
                "discipline": "Civil",
                "location": loc,
                "activity_description": desc,
                "status": status,
                "actual_start": parsed_date if status == "in_progress" else None,
                "actual_end": parsed_date if status == "completed" else None,
                "progress": progress,
                "equipment_or_tag": None,
                "confidence": 0.91,
            })

        # Check for Civil / Rebar fixing / Reinforcement (Multi-activity Granularity Handling)
        if "rebar" in lowered or "reinforcement" in lowered:
            is_start = ("start" in lowered or "started" in lowered or "commenced" in lowered)
            status = "in_progress" if is_start else ("completed" if ("completed" in lowered or "finished" in lowered) else "in_progress")
            progress = 100.0 if status == "completed" else (25.0 if is_start else float(self._percentage(lowered, 35)))
            observations.append({
                "discipline": "Civil",
                "location": "Unit 1" if "unit 1" in lowered else ("East Foundation" if "east" in lowered else None),
                "activity_description": "Rebar fixing and reinforcement",
                "status": status,
                "actual_start": parsed_date if is_start else None,
                "actual_end": parsed_date if status == "completed" else None,
                "progress": progress,
                "equipment_or_tag": None,
                "confidence": 0.90,
            })

        # Check for Electrical / Cable Tray / Transformer
        if "cable tray" in lowered or "transformer" in lowered or "electrical" in lowered:
            status = "completed" if ("complete" in lowered or "completed" in lowered) else "in_progress"
            progress = 100.0 if status == "completed" else float(self._percentage(lowered, 45))
            loc = "Substation" if "substation" in lowered else ("Unit 2" if "unit 2" in lowered else None)
            desc = "Install transformer foundation" if "transformer" in lowered else "Cable tray installation"
            observations.append({
                "discipline": "Electrical",
                "location": loc,
                "activity_description": desc,
                "status": status,
                "actual_start": None,
                "actual_end": None,
                "progress": progress,
                "equipment_or_tag": "TR-01" if "transformer" in lowered else None,
                "confidence": 0.92,
            })

        # Fallback if no specific keyword matched
        if not observations:
            status = "completed" if "complete" in lowered or "completed" in lowered else "in_progress"
            progress = 100.0 if status == "completed" else float(self._percentage(lowered, 30))
            observations.append({
                "discipline": None,
                "location": None,
                "activity_description": raw_text[:200].strip() or "reported field activity",
                "status": status,
                "actual_start": None,
                "actual_end": None,
                "progress": progress,
                "confidence": 0.70,
            })

        delay_info = self._extract_delay_info(raw_text)
        for obs in observations:
            for k, v in delay_info.items():
                if obs.get(k) is None:
                    obs[k] = v

        return json.dumps({"observations": observations})

    @staticmethod
    def _extract_delay_info(text: str) -> dict[str, object]:
        lowered = text.lower()
        delay_cause: str | None = None
        patterns = [
            r"(?:delayed|delayed\s+due\s+to|delayed\s+by|delayed\s+because\s+of|held\s+up\s+(?:due\s+to|by|because\s+of)?|on\s+hold\s+pending|pending)\s+([^.,;\n]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                if extracted.lower().startswith("due to "):
                    extracted = extracted[7:].strip()
                delay_cause = extracted.capitalize()
                break

        if "delay" in lowered or "delayed" in lowered or "on hold" in lowered:
            if not delay_cause:
                return {
                    "delay_cause": "UNKNOWN",
                    "delay_category": "UNKNOWN",
                    "constraint": None,
                    "impact_description": "Activity delayed without specific cause stated.",
                    "delay_confidence": 0.5,
                }

            dc_lower = delay_cause.lower()
            if any(w in dc_lower for w in ["ndt", "inspection", "qc", "radiography", "testing", "clearance"]):
                category = "INSPECTION"
            elif any(w in dc_lower for w in ["approval", "permit", "sign-off", "ptw", "clearance"]):
                category = "APPROVAL"
            elif any(w in dc_lower for w in ["material", "delivery", "shortage", "spool", "valve", "fittings"]):
                category = "MATERIAL"
            elif any(w in dc_lower for w in ["manpower", "labor", "labour", "crew", "welder", "strike"]):
                category = "MANPOWER"
            elif any(w in dc_lower for w in ["crane", "rigging", "equipment", "breakdown", "generator"]):
                category = "EQUIPMENT"
            elif any(w in dc_lower for w in ["weather", "rain", "monsoon", "wind", "heat"]):
                category = "WEATHER"
            elif any(w in dc_lower for w in ["access", "scaffold", "scaffolding", "front"]):
                category = "ACCESS"
            elif any(w in dc_lower for w in ["drawing", "design", "rfi", "isometric"]):
                category = "DESIGN"
            elif any(w in dc_lower for w in ["predecessor", "dependency", "upstream"]):
                category = "DEPENDENCY"
            elif any(w in dc_lower for w in ["contractor", "subcontractor"]):
                category = "CONTRACTOR"
            elif any(w in dc_lower for w in ["logistics", "transport", "freight"]):
                category = "LOGISTICS"
            elif any(w in dc_lower for w in ["safety", "hazard", "incident"]):
                category = "SAFETY"
            else:
                category = "OTHER"

            return {
                "delay_cause": delay_cause,
                "delay_category": category,
                "constraint": delay_cause,
                "impact_description": f"Activity delayed due to {delay_cause}",
                "delay_confidence": 0.94,
            }

        return {
            "delay_cause": None,
            "delay_category": None,
            "constraint": None,
            "impact_description": None,
            "delay_confidence": None,
        }


    def normalize_activity(self, prompt: str) -> str:
        match = re.search(r"INPUT_JSON:\s*(\{.*\})", prompt, flags=re.DOTALL)
        payload = json.loads(match.group(1)) if match else {}
        raw_text = str(payload.get("activity_description") or payload.get("raw_text") or prompt)
        lowered = raw_text.lower()
        if "valve" in lowered or "bolt-up" in lowered:
            description = "install piping assembly" if "assembly" in lowered or "bolt-up" in lowered or "xv-203" in lowered else "valve installation"
            discipline = "Piping"
            location = payload.get("location") or ("Unit 3" if "unit 3" in lowered else None)
        elif "hydrotest" in lowered:
            description = "hydrotest line 18-aa" if "18" in lowered else "hydrotest preparation"
            discipline = "Piping"
            location = payload.get("location") or ("Unit 3" if "unit 3" in lowered else None)
        elif "24 inch" in lowered and ("line" in lowered or "erection" in lowered):
            description = "24 inch line erection"
            discipline = "Piping"
            location = payload.get("location") or ("Unit 3" if "unit 3" in lowered else None)
        else:
            description = raw_text.strip().lower()
            discipline = payload.get("discipline")
            location = payload.get("location")
        return json.dumps({
            "normalized_activity_description": description,
            "normalized_discipline": discipline,
            "normalized_location": location,
            "confidence": 0.75,
        })

    def explain_reconciliation(self, prompt: str) -> str:
        is_conflict = "conflict" in prompt.lower() or "80%" in prompt or "80.0%" in prompt
        status = "in_progress" if is_conflict else "completed"
        progress = 85.0 if is_conflict else 100.0
        confidence = 0.65 if is_conflict else 0.95
        reasoning = (
            "Independent sources report conflicting progress; planner review required."
            if is_conflict
            else "Independent evidence sources agree on activity completion."
        )
        return json.dumps({
            "recommended_status": status,
            "recommended_progress": progress,
            "evidence_assessment": "Deterministic mock evidence assessment.",
            "conflict_detected": is_conflict,
            "conflict_summary": "Conflicting progress between sources" if is_conflict else None,
            "reasoning": reasoning,
            "confidence": confidence,
            "supporting_observations": [],
            "contradictory_observations": [],
            "explanation": reasoning,
        })


    @staticmethod
    def _parse_extracted_date(text: str) -> str | None:
        lowered = text.lower()
        if "today" in lowered:
            return "2026-09-14"
        if "yesterday" in lowered:
            return "2026-09-13"

        iso_match = re.search(r"\b(202\d-\d{2}-\d{2})\b", text)
        if iso_match:
            return iso_match.group(1)

        month_map = {
            "jan": "01", "january": "01", "feb": "02", "february": "02",
            "mar": "03", "march": "03", "apr": "04", "april": "04",
            "may": "05", "jun": "06", "june": "06", "jul": "07", "july": "07",
            "aug": "08", "august": "08", "sep": "09", "september": "09",
            "oct": "10", "october": "10", "nov": "11", "november": "11",
            "dec": "12", "december": "12",
        }
        m1 = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            lowered,
        )
        if m1:
            m_str = month_map[m1.group(1)]
            d_str = f"{int(m1.group(2)):02d}"
            return f"2026-{m_str}-{d_str}"

        m2 = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
            lowered,
        )
        if m2:
            d_str = f"{int(m2.group(1)):02d}"
            m_str = month_map[m2.group(2)]
            return f"2026-{m_str}-{d_str}"

        return None

    @staticmethod
    def _input_text(prompt: str) -> str:
        match = re.search(r"INPUT_JSON:\s*(\{.*\})", prompt, flags=re.DOTALL)
        if not match:
            return prompt
        payload = json.loads(match.group(1))
        return str(payload.get("raw_text") or payload.get("activity_description") or "")

    @staticmethod
    def _percentage(text: str, default: int) -> int:
        match = re.search(r"(\d{1,3})\s*%", text)
        return int(match.group(1)) if match else default


class DeterministicEmbeddingProvider:
    """Stable local embeddings for development and tests; no network or API key required."""

    dimensions = 128

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            # Synonyms make common field phrasing comparable before hashing.
            token = {"erection": "erect", "installed": "install", "installation": "install",
                     "piping": "pipe", "welding": "weld", "inches": "inch"}.get(token, token)
            index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimensions
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector
