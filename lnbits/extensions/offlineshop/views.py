import time
from datetime import datetime
from http import HTTPStatus
from typing import List

from fastapi import HTTPException, Request
from fastapi.params import Depends, Query
from starlette.responses import HTMLResponse

from lnbits.core.crud import get_standalone_payment
from lnbits.core.models import Payment, User
from lnbits.core.views.api import api_payment
from lnbits.decorators import check_user_exists

from . import offlineshop_ext, offlineshop_renderer
from .crud import get_item, get_shop
from .models import Item


@offlineshop_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return offlineshop_renderer().TemplateResponse(
        "offlineshop/index.html", {"request": request, "user": user.dict()}
    )


@offlineshop_ext.get("/print", response_class=HTMLResponse)
async def print_qr_codes(request: Request, items: List[int] = None):
    items = []
    for item_id in request.query_params.get("items").split(","):
        item = await get_item(item_id)  # type: Item
        if item:
            items.append(
                {
                    "lnurl": item.lnurl(request),
                    "name": item.name,
                    "price": f"{item.price} {item.unit}",
                }
            )

    return offlineshop_renderer().TemplateResponse(
        "offlineshop/print.html", {"request": request, "items": items}
    )


@offlineshop_ext.get(
    "/confirmation/{p}",
    name="offlineshop.confirmation_code",
    response_class=HTMLResponse,
)
async def confirmation_code(p: str = Query(...)):
    style = "<style>* { font-size: 100px}</style>"

    payment_hash = p
    await api_payment(payment_hash)
    payment: Payment = await get_standalone_payment(payment_hash)
    if not payment:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Couldn't find the payment {payment_hash}." + style,
        )
    if payment.pending:
        raise HTTPException(
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            detail=f"Payment {payment_hash} wasn't received yet. Please try again in a minute."
            + style,
        )

    if payment.time + 60 * 15 < time.time():
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_TIMEOUT,
            detail="Too much time has passed." + style,
        )

    item = await get_item(payment.extra.get("item"))
    shop = await get_shop(item.shop)

    return (
        f"""
[{shop.get_code(payment_hash)}]<br>
{item.name}<br>
{item.price} {item.unit}<br>
{datetime.utcfromtimestamp(payment.time).strftime('%Y-%m-%d %H:%M:%S')}
    """
        + style
    )
