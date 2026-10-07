import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import germinate
from output_columns import output_value, validate_columns

ROOT = Path(__file__).resolve().parents[1]


class OutputTests(unittest.TestCase):
    def result(self, **changes):
        result = germinate.Result("RED PAC", "html_search", "Título original", "https://example.org/call",
                                  "candidate", 5, "grant", "soil", "", "2026-09-22T12:00:00+00:00", "")
        for key, value in changes.items():
            setattr(result, key, value)
        return result

    def test_default_layout_manual_blanks_and_unknown_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.csv"
            germinate.write_csv([self.result()], path)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                row = next(reader)
                self.assertEqual(reader.fieldnames, [
                    "Titulo", "Entidad Financiadora", "Programa", "Nivel", "Temas", "Fecha límite",
                    "Frequencia", "URL (link)", "Max Budget (€)", "Estatus", "¿Experiencia?",
                    "Requisitos", "_Documento de trabajo asociado", "Donde encontrado / como nos enteramos?",
                    "Decisión IA", "Publicación", "Motivo IA", "Confianza"])
            for key in ("¿Experiencia?", "_Documento de trabajo asociado", "Donde encontrado / como nos enteramos?",
                        "Decisión IA", "Publicación", "Entidad Financiadora"):
                self.assertEqual(row[key], "")
            self.assertEqual(row["Estatus"], "Pendiente")
            self.assertNotIn("Regla inicial", row)

    def test_reorder_rename_remove_and_empty_output(self):
        config = {"columns": [{"label": "Enlace", "field": "url"}, {"label": "Ayuda", "field": "title"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.csv"
            germinate.write_csv([self.result()], path, config)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(list(csv.reader(handle)), [
                    ["Enlace", "Ayuda"], ["https://example.org/call", "Título original"]])
            germinate.write_csv([], path, config)
            self.assertEqual(path.read_text(encoding="utf-8-sig"), "Enlace,Ayuda\n")

    def test_bad_columns_do_not_overwrite_existing_file(self):
        for columns in ([], [{"label": "X", "field": "typo"}],
                        [{"label": "X", "field": "url"}, {"label": "X", "field": "title"}]):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "result.csv"
                path.write_text("keep me")
                with self.assertRaises(ValueError):
                    germinate.write_csv([], path, {"columns": columns})
                self.assertEqual(path.read_text(), "keep me")

    def test_status_is_not_inferred_from_future_deadline(self):
        base = {"checked_at": "2026-09-22T12:00:00+00:00", "deadline": "2026-12-01"}
        for status in ("unknown", "closed", "upcoming", ""):
            self.assertEqual(output_value(dict(base, application_status=status), "status"), "Pendiente")
        self.assertEqual(output_value(dict(base, application_status="open"), "status"), "En curso")
        for deadline in ("2026-09-21", "unknown date"):
            self.assertEqual(output_value(dict(base, application_status="open", deadline=deadline), "status"), "Pendiente")
        for deadline in ("2026-09-22", ""):
            self.assertEqual(output_value(dict(base, application_status="open", deadline=deadline), "status"), "En curso")

    def test_no_implicit_currency_conversion_and_preserve_zero(self):
        for currency in ("USD", "", None):
            self.assertEqual(output_value({"currency": currency, "amount_max": 5000}, "budget_eur"), "")
        self.assertEqual(output_value({"currency": "EUR", "amount_max": 0}, "budget_eur"), 0)
        self.assertEqual(output_value({"currency": "EUR", "amount_max": 5000}, "budget_eur"), 5000)

    def test_enrichment_populates_new_fields_and_preserves_rule(self):
        answer = {
            "title": "Título oficial", "decision": "accept", "confidence": 0.7, "grant_status": "confirmed",
            "deadline": "2026-12-01", "amount_min": 0, "amount_max": 10000, "currency": "EUR",
            "eligible_countries": ["España"], "eligible_applicants": ["Asociaciones"],
            "topics": ["Agricultura"], "consortium_required": None, "decision_reason": "Información parcial.",
            "funder": "Entidad", "program": "Programa", "level": "Regional", "frequency": "Anual",
            "requirements": "Asociaciones rurales.", "publication_date": "2026-09-01", "application_status": "open"
        }
        result = self.result()
        with patch("germinate.OpenAIAgent") as agent, patch("germinate.fetch_html", return_value="<p>Grant</p>"):
            agent.return_value.analyze.return_value = answer
            errors = germinate.enrich([result], {"max_pages_per_run": 1, "minimum_confidence": 0.8})
        self.assertEqual(errors, [])
        self.assertEqual(result.title, "Título oficial")
        for field in ("funder", "program", "level", "frequency", "requirements", "publication_date", "application_status"):
            self.assertEqual(getattr(result, field), answer[field])
        self.assertEqual(result.amount_min, 0)
        self.assertEqual(result.decision, "candidate")
        self.assertEqual(result.agent_decision, "review")
        self.assertEqual(result.agent_reason, "Información parcial.")

    def test_schema_requires_new_fields_and_restricts_level(self):
        schema = json.loads((ROOT / "agent/schema.json").read_text())
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertEqual(schema["properties"]["level"]["enum"], ["Ciudad", "Regional", "Nacional", "EU", "Global", None])


if __name__ == "__main__":
    unittest.main()
