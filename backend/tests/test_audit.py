"""Hash-chain audit ledger tests — tampering must be detected."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.session import engine  # noqa: F401 (ensures models registered)
from app.services.audit import append_entry, verify_chain


@pytest.fixture()
def session():
    # separate in-memory DB so tests never touch the real one
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    S = sessionmaker(bind=test_engine)
    s = S()
    yield s
    s.close()


def test_chain_verifies_when_clean(session):
    append_entry(session, actor="a", action="x")
    append_entry(session, actor="b", action="y")
    session.commit()
    assert verify_chain(session)["valid"] is True
    assert verify_chain(session)["checked"] == 2


def test_chain_detects_entry_tampering(session):
    e1 = append_entry(session, actor="a", action="x")
    append_entry(session, actor="b", action="y")
    session.commit()
    # tamper with a payload after the fact
    session.query(type(e1)).filter_by(seq=e1.seq).update({"action": "FORGERY"})
    session.commit()
    assert verify_chain(session)["valid"] is False


def test_chain_links_prev_hash(session):
    e1 = append_entry(session, actor="a", action="x")
    e2 = append_entry(session, actor="b", action="y")
    session.commit()
    assert e2.prev_hash == e1.entry_hash
