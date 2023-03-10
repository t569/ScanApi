
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import Response, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
import qrcode
from io import BytesIO
from . import schemas, models
from sqlalchemy.orm import Session
from .database import SessionLocal, engine
from passlib.context import CryptContext
import validators

app = FastAPI()

models.Base.metadata.create_all(bind=engine)


# create dependencies
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# problem line/function does not like coroutine, accepts binary data instead

# code to generate qr_code
def generate_qr_code(link):
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=5
    )
    qr.add_data(link)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white')

    with BytesIO() as file:
        img.save(file, 'PNG')
        file.seek(0)
        binary_data = file.read()
    return binary_data


# code for generation and validation of password
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


@app.get("/")
def home():
    return "File Sharing service"


@app.post("/endpoint/", response_model=schemas.EndPoint)
def create_file_code(endpoint: schemas.EndPointCreate, db: Session = Depends(get_db)):
    # validate url
    if not validators.url(endpoint.url):
        raise HTTPException(detail="file endpoint does not exist", status_code=status.HTTP_404_NOT_FOUND)

    # check if name of file already exists
    ed_get = db.query(models.FileModel).filter(models.FileModel.name == endpoint.name).first()

    # if file doesn't exist

    if not ed_get:
        # generate qr_code data
        code_data = generate_qr_code(endpoint.url)

        ed_get = models.FileModel(name=endpoint.name, qr_code=code_data,
                                  url=endpoint.url, password=get_password_hash(endpoint.password))

        # commit changes to database
        db.add(ed_get)
        db.commit()
        db.refresh(ed_get)

    return endpoint

# learn how to use passwords and dependencies


@app.get('/endpoints/{ed_name}')
def return_file_code(ed_name: str,
                     form_data: schemas.PasswordForm = Depends(),
                     db: Session = Depends(get_db)):

    endpoint = db.query(models.FileModel).filter(models.FileModel.name == ed_name).first()
    # check if endpoint does not exist raise error if so
    if not endpoint:
        raise HTTPException(detail=f'{ed_name} does not exist', status_code=404)
    # check if file already exists
    #####
    #####
    #
    # check if the password is correct4
    # problem line of code
    if not verify_password(form_data.password, endpoint.password):
        raise HTTPException(status_code=400, detail='Invalid Password')

    qr_code = endpoint.qr_code

    return Response(content=qr_code, media_type='image/png')


# to allow databases to be read directly like this add orm_mode = True under class config in schemas
@app.get('/endpoints/', response_model=list[schemas.EndPoint])
def return_files(skip: int, limit: int, db: Session = Depends(get_db)):
    return db.query(models.FileModel).offset(skip).limit(limit).all()


@app.patch('/endpoint/{ed_name}')
async def update_file(ed_name: str, endpoint: schemas.EndpointUpdate, db: Session = Depends(get_db)):

    # find the stored file
    stored_ed = db.query(models.FileModel).filter(models.FileModel.name == ed_name).first()

    # have to change this to make the code better later though, will give problems
    stored_file_dict = {
        'name': stored_ed.name,
        'url': stored_ed.url,
        'password': get_password_hash(stored_ed.password)
    }

    stored_file_model = schemas.EndpointUpdate(**stored_file_dict)
    update_data = endpoint.dict(exclude_unset=True)
    updated_file = stored_file_model.copy(update=update_data)


# raise a better request validation error for user requests
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # log the request body into the error
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({'detail': exc.errors(), 'body': exc.body})
    )
