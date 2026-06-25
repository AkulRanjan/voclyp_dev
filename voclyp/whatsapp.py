"""WhatsApp integration for product recommendations via Twilio.

Supports:
- Queuing recommendations for async delivery
- Twilio Messaging API integration (when configured)
- Delivery status tracking (pending, delivered, failed)
- Idempotency (same message not sent twice)
"""
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .contracts import utcnow


def _utc_now():
    """UTC timestamp for consistency with the rest of VoClyp."""
    return datetime.now(timezone.utc).isoformat()


class WhatsAppQueue:
    """Queue for WhatsApp message delivery via Twilio.

    For MVP: queues and tracks delivery status locally.
    Actual Twilio sending can be done via a separate worker service.
    """

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()
        self._conn.commit()

    def _init_schema(self):
        """Initialize WhatsApp queue tables."""
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            message_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            customer_phone TEXT NOT NULL,
            rep_name TEXT,
            products TEXT NOT NULL,  -- JSON array of product objects
            message_body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending|queued|delivered|failed
            attempt_count INTEGER NOT NULL DEFAULT 0,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            delivered_at TEXT,
            failed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_whatsapp_status ON whatsapp_messages(status);
        CREATE INDEX IF NOT EXISTS idx_whatsapp_customer ON whatsapp_messages(customer_phone);
        CREATE INDEX IF NOT EXISTS idx_whatsapp_conversation ON whatsapp_messages(conversation_id);
        """)

    def queue_message(self, tenant_id: str, conversation_id: str, customer_phone: str,
                      products: list, message_body: str, message_id: str = None,
                      rep_name: str = None) -> str:
        """Queue a WhatsApp message for delivery.

        Args:
            tenant_id: Tenant ID
            conversation_id: Associated conversation ID
            customer_phone: Customer phone number in E.164 format
            products: List of product objects
            message_body: Message text to send
            message_id: Optional explicit message ID (for idempotency)
            rep_name: Sales rep name

        Returns:
            message_id (UUID-like string)
        """
        import secrets
        if not message_id:
            message_id = f"whatsapp-msg-{secrets.token_hex(8)}"

        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO whatsapp_messages
                       (message_id, tenant_id, conversation_id, customer_phone,
                        rep_name, products, message_body, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (message_id, tenant_id, conversation_id, customer_phone,
                     rep_name, json.dumps(products), message_body, "pending", _utc_now())
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                # Idempotent: return existing if duplicate
                pass

        return message_id

    def get_message(self, message_id: str) -> Optional[dict]:
        """Get message status and details."""
        row = self._conn.execute(
            """SELECT message_id, tenant_id, conversation_id, customer_phone,
                      rep_name, products, message_body, status, attempt_count,
                      error_detail, created_at, sent_at, delivered_at
               FROM whatsapp_messages WHERE message_id=?""",
            (message_id,)
        ).fetchone()

        if not row:
            return None

        return {
            "message_id": row[0],
            "tenant_id": row[1],
            "conversation_id": row[2],
            "customer_phone": row[3],
            "rep_name": row[4],
            "products": json.loads(row[5]),
            "message_body": row[6],
            "status": row[7],  # pending|queued|delivered|failed
            "attempt_count": row[8],
            "error_detail": row[9],
            "created_at": row[10],
            "sent_at": row[11],
            "delivered_at": row[12],
        }

    def list_messages_for_customer(self, customer_phone: str, limit: int = 20) -> list:
        """List all recommendations sent to a customer."""
        rows = self._conn.execute(
            """SELECT message_id, conversation_id, products, status, created_at
               FROM whatsapp_messages
               WHERE customer_phone=?
               ORDER BY created_at DESC
               LIMIT ?""",
            (customer_phone, limit)
        ).fetchall()

        return [
            {
                "message_id": r[0],
                "conversation_id": r[1],
                "products": json.loads(r[2]),
                "status": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def mark_queued(self, message_id: str) -> bool:
        """Mark a message as queued (about to send to Twilio)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE whatsapp_messages SET status='queued' WHERE message_id=?",
                (message_id,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def mark_delivered(self, message_id: str) -> bool:
        """Mark a message as delivered."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE whatsapp_messages
                   SET status='delivered', delivered_at=?
                   WHERE message_id=?""",
                (_utc_now(), message_id)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def mark_failed(self, message_id: str, error: str = None, attempt_count: int = 1) -> bool:
        """Mark a message as failed with optional error detail."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE whatsapp_messages
                   SET status='failed', failed_at=?, error_detail=?, attempt_count=?
                   WHERE message_id=?""",
                (_utc_now(), error, attempt_count, message_id)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def pending_messages(self, limit: int = 100) -> list:
        """Get pending messages ready to be sent to Twilio."""
        rows = self._conn.execute(
            """SELECT message_id, customer_phone, message_body, products
               FROM whatsapp_messages
               WHERE status='pending'
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()

        return [
            {
                "message_id": r[0],
                "customer_phone": r[1],
                "message_body": r[2],
                "products": json.loads(r[3]),
            }
            for r in rows
        ]
