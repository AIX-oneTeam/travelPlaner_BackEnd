import logging
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.data_models.data_model import ImageUrl
logger = logging.getLogger(__name__)



async def save_image_url(image_url:str, image_name:str, session: AsyncSession):
    query = select(ImageUrl).where(ImageUrl.name == image_name)
    result = await session.exec(query)
    existing_image = result.first()

    if existing_image:
        existing_image.url = image_url
        session.add(existing_image)
        await session.commit()
    session.add(ImageUrl(name=image_name, url=image_url))

async def get_image_url(image_name: str, session: AsyncSession) -> str | None:
    query = select(ImageUrl).where(ImageUrl.name == image_name)
    result = await session.exec(query)
    image_url = result.first()
    if image_url:
        return image_url.url
    else:
        return None