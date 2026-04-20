from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request):
    probe = getattr(request.app.state, "connectivity", None)
    online = probe.is_online() if probe else None
    return {"status": "ok", "online": online}
