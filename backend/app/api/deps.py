from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db import get_db

DbDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
require_owner = Depends(get_current_user)
