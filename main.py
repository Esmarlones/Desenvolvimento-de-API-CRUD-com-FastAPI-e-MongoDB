from contextlib import asynccontextmanager
from os import getenv
from typing import Annotated

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import MongoClient
from pymongo.collection import Collection
from dotenv import load_dotenv


load_dotenv()

MONGODB_URL = getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DATABASE = getenv("MONGODB_DATABASE", "atividade_crud")

client: MongoClient | None = None
products: Collection | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global client, products

    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        client = None
        raise

    products = client[MONGODB_DATABASE]["products"]
    yield

    client.close()
    client = None
    products = None


app = FastAPI(
    title="API de Produtos",
    description="API REST para cadastro de produtos com FastAPI e MongoDB.",
    version="1.0.0",
    lifespan=lifespan,
)


class ProductBase(BaseModel):
    name: str = Field(min_length=2, max_length=100, examples=["Teclado mecânico"])
    description: str | None = Field(
        default=None,
        max_length=500,
        examples=["Teclado ABNT2 com iluminação RGB"],
    )
    price: float = Field(gt=0, examples=[249.90])
    stock: int = Field(ge=0, examples=[15])
    category: str = Field(min_length=2, max_length=60, examples=["Informática"])


class ProductCreate(ProductBase):
    model_config = ConfigDict(extra="forbid")


class ProductUpdate(ProductBase):
    model_config = ConfigDict(extra="forbid")


class ProductResponse(ProductBase):
    id: str


def get_collection() -> Collection:
    if products is None:
        raise RuntimeError("A conexão com o MongoDB não foi inicializada.")
    return products


def parse_object_id(product_id: str) -> ObjectId:
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de produto inválido.",
        )
    return ObjectId(product_id)


def serialize_product(document: dict) -> ProductResponse:
    return ProductResponse(
        id=str(document["_id"]),
        name=document["name"],
        description=document.get("description"),
        price=document["price"],
        stock=document["stock"],
        category=document["category"],
    )


@app.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar um produto",
)
def create_product(product: ProductCreate) -> ProductResponse:
    collection = get_collection()
    document = product.model_dump()
    result = collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_product(document)


@app.get(
    "/products",
    response_model=list[ProductResponse],
    summary="Listar todos os produtos",
)
def list_products() -> list[ProductResponse]:
    return [serialize_product(document) for document in get_collection().find()]


@app.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Consultar um produto pelo ID",
)
def get_product(
    product_id: Annotated[str, Path(description="ID gerado pelo MongoDB")],
) -> ProductResponse:
    document = get_collection().find_one({"_id": parse_object_id(product_id)})
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )
    return serialize_product(document)


@app.put(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Atualizar um produto",
)
def update_product(
    product_id: Annotated[str, Path(description="ID gerado pelo MongoDB")],
    product: ProductUpdate,
) -> ProductResponse:
    collection = get_collection()
    object_id = parse_object_id(product_id)
    result = collection.update_one(
        {"_id": object_id},
        {"$set": product.model_dump()},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )

    document = collection.find_one({"_id": object_id})
    return serialize_product(document)


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir um produto",
)
def delete_product(
    product_id: Annotated[str, Path(description="ID gerado pelo MongoDB")],
) -> Response:
    result = get_collection().delete_one({"_id": parse_object_id(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
