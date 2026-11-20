import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app


class SupportFlowTests(unittest.TestCase):
    def setUp(self):
        self.previous_db_path = app.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        app.initialize_database()
        self.client = TestClient(app.app)

    def tearDown(self):
        self.client.close()
        app.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    def test_chat_uses_order_id_in_message_and_cites_policy(self):
        response = self.client.post(
            "/api/chat",
            json={
                "message": "My earbuds are defective and won't turn on. #VT-1043",
                "order_id": "VT-1042",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["order"]["id"], "VT-1043")
        self.assertTrue(body["eligible"])
        self.assertTrue(any("Returns & Exchanges Section 2.1, p. 2" == s["citation"] for s in body["sources"]))
        self.assertNotIn("According to", body["answer"])

    def test_chat_covers_more_faq_topics_and_paraphrases(self):
        examples = [
            ("How long do I have to send my laptop back?", "30-Day Returns"),
            ("Can I cancel my order before it ships?", "Order Changes & Cancellations"),
            ("How do I get another copy of my payment receipt?", "Payment & Receipts"),
            ("Tracking says delivered but my parcel is missing.", "Delivery Delays & Missing Parcels"),
            ("How do I safely troubleshoot a device that will not power on?", "Safe Device Checks"),
        ]
        for question, expected_title in examples:
            with self.subTest(question=question):
                response = self.client.post("/api/chat", json={"message": question})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertTrue(body["sources"])
                self.assertEqual(body["sources"][0]["title"], expected_title)
                self.assertIn("Section", body["sources"][0]["citation"])

    def test_write_waits_for_approval_before_changing_order(self):
        prepared = self.client.post(
            "/api/actions/prepare",
            json={"order_id": "VT-1043", "action_type": "refund", "reason": "Defective earbuds"},
        )
        self.assertEqual(prepared.status_code, 200)
        action = prepared.json()
        self.assertEqual(action["status"], "awaiting_approval")
        self.assertEqual(self.client.get("/api/orders/VT-1043").json()["status"], "delivered")

        decided = self.client.post(
            f"/api/actions/{action['action_id']}/approval",
            json={"approved": True, "approved_by": "customer"},
        )
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(decided.json()["status"], "approved")
        self.assertEqual(self.client.get("/api/orders/VT-1043").json()["status"], "refund_issued")
        duplicate = self.client.post(
            "/api/actions/prepare",
            json={"order_id": "VT-1043", "action_type": "replacement", "reason": "Defective earbuds"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_high_value_order_is_escalated_without_automated_write(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Can I return this defective laptop? #VT-1042", "order_id": "VT-1042"},
        )

        body = response.json()
        self.assertFalse(body["eligible"])
        self.assertEqual(body["escalation"]["reason"], "high_value")
        self.assertEqual(self.client.get("/api/orders/VT-1042").json()["status"], "delivered")

    def test_unsupported_policy_question_is_not_guessed(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Can you cover my custom-built drone? #VT-1043", "order_id": "VT-1043"},
        )

        body = response.json()
        self.assertEqual(body["sources"], [])
        self.assertIn("won't guess", body["answer"])
        self.assertEqual(body["escalation"]["reason"], "uncertain")

    def test_exchange_request_explains_policy_gap_and_high_value_handoff(self):
        response = self.client.post(
            "/api/chat",
            json={
                "message": "Can I exchange the laptop instead of returning it? #VT-1042",
                "order_id": "VT-1042",
            },
        )

        body = response.json()
        self.assertIn("doesn't say whether exchanges are available", body["answer"])
        self.assertIn("sent this to support to check", body["answer"])
        self.assertEqual(body["escalation"]["reason"], "high_value")
        self.assertFalse(body["eligible"])

    def test_return_answer_is_conversational_and_explains_high_value_review(self):
        body = self.client.post(
            "/api/chat",
            json={"message": "Can I still return my laptop?", "order_id": "VT-1042"},
        ).json()

        self.assertIn("Your VoltBook Pro 14-inch was delivered 20 days ago", body["answer"])
        self.assertIn("inside the 30-day return window", body["answer"])
        self.assertIn("support specialist needs to review it", body["answer"])
        self.assertNotIn("Most VoltTech products may be returned", body["answer"])
        self.assertTrue(body["sources"][0]["citation"])

    def test_order_context_is_kept_when_returns_policy_is_not_top_result(self):
        retrieved = [
            {
                "title": "Shipping & Delivery",
                "text": "Standard delivery policy.",
                "excerpt": "Standard delivery policy.",
                "citation": "Shipping Section 1, p. 1",
            },
            {
                "title": "30-Day Returns",
                "text": "Return policy.",
                "excerpt": "Return policy.",
                "citation": "Returns Section 2, p. 2",
            },
        ]
        with patch("app.retrieve_policies", return_value=retrieved):
            body = self.client.post(
                "/api/chat",
                json={"message": "Where is my order?", "order_id": "VT-1042"},
            ).json()

        self.assertIn("I found order **#VT-1042**", body["answer"])
        self.assertIn("its warranty is active", body["answer"])

    def test_contact_and_exchange_location_questions_are_not_guessed(self):
        questions = [
            "Where can I drop off my return?",
            "What number should I call for support?",
        ]
        for question in questions:
            with self.subTest(question=question):
                body = self.client.post("/api/chat", json={"message": question}).json()
                self.assertIn("don't have a verified store address or phone number", body["answer"])
                self.assertEqual(body["escalation"]["reason"], "uncertain")

    def test_frustration_and_possible_exclusion_are_escalated(self):
        frustrated = self.client.post(
            "/api/chat",
            json={"message": "This is unacceptable, replace my defective earbuds. #VT-1043"},
        ).json()
        damaged = self.client.post(
            "/api/chat",
            json={"message": "Water got into my VoltBuds and they are damaged. #VT-1043"},
        ).json()

        self.assertEqual(frustrated["escalation"]["reason"], "customer_frustration")
        self.assertFalse(frustrated["eligible"])
        self.assertEqual(damaged["escalation"]["reason"], "uncertain")
        self.assertFalse(damaged["eligible"])

    def test_expired_return_and_warranty_is_escalated(self):
        with closing(app.connect()) as db:
            db.execute("UPDATE orders SET delivered_at = '2024-01-01' WHERE id = 'VT-1043'")
            db.commit()
        response = self.client.post(
            "/api/chat",
            json={"message": "Can I get a refund for defective earbuds? #VT-1043"},
        )

        self.assertEqual(response.json()["escalation"]["reason"], "out_of_policy")
        self.assertFalse(response.json()["eligible"])

    def test_action_rejects_non_defect_and_high_value_requests(self):
        no_defect = self.client.post(
            "/api/actions/prepare",
            json={"order_id": "VT-1043", "action_type": "refund", "reason": "Changed my mind"},
        )
        high_value = self.client.post(
            "/api/actions/prepare",
            json={"order_id": "VT-1042", "action_type": "replacement", "reason": "Defective screen"},
        )

        self.assertEqual(no_defect.status_code, 409)
        self.assertEqual(high_value.status_code, 409)


if __name__ == "__main__":
    unittest.main()
