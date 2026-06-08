from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteRead

router = APIRouter()


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate, db: Session = Depends(get_db_session)) -> Site:
    site = Site(
        site_key=payload.site_key,
        site_name=payload.site_name,
        base_url=payload.base_url,
        webhook_secret=payload.webhook_secret,
        api_token=payload.api_token,
        status=payload.status,
    )
    db.add(site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="site already exists") from exc
    db.refresh(site)
    return site


@router.get("", response_model=list[SiteRead])
def list_sites(db: Session = Depends(get_db_session)) -> list[Site]:
    return db.query(Site).order_by(Site.id.desc()).all()
