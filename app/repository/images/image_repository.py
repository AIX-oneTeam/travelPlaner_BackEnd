import logging
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.data_models.data_model import ImageUrl
logger = logging.getLogger(__name__)



async def save_image_url(image_url: ImageUrl, session: AsyncSession):
    query = select(ImageUrl).where(ImageUrl.name == image_url.name)
    result = await session.exec(query)
    existing_image = result.first()

    if existing_image:
        existing_image.url = image_url.url
        session.add(existing_image)
        await session.commit()
    session.add(image_url)

async def get_image_url(name: str, session: AsyncSession) -> str:
    query = select(ImageUrl).where(ImageUrl.name == name)
    result = await session.exec(query)
    image_url = result.first()
    return image_url.url





