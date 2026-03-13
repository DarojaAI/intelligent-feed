"""FastAPI outcomes endpoint for agent callbacks"""

import logging
from typing import Optional

import ulid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from intel.config import Config
from intel.db import init_db, insert_agent_outcome

logger = logging.getLogger(__name__)

app = FastAPI(title="Intelligence Feed Outcomes API")


class OutcomeReport(BaseModel):
    payload_id: str
    action_id: str
    outcome: str  # "executed" | "skipped" | "escalated" | "failed"
    detail: Optional[str] = None


@app.post("/api/outcomes")
async def receive_outcome(report: OutcomeReport):
    """Receive agent outcome report"""
    try:
        conn = init_db(Config().db_path)
        outcome_id = ulid.new().str

        insert_agent_outcome(
            conn,
            outcome_id=outcome_id,
            payload_id=report.payload_id,
            action_id=report.action_id,
            outcome=report.outcome,
            detail=report.detail,
        )

        logger.info(f"Received outcome: {report.outcome} for {report.action_id}")
        return {"status": "ok", "outcome_id": outcome_id}

    except Exception as e:
        logger.error(f"Error receiving outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
