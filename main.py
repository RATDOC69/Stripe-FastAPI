import os
import stripe
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from bcrypt import checkpw
from dotenv import load_dotenv
from model.user_connection import UserConnection
from schema.user_schema import UserSchema
from starlette.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT

fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "$2y$12$yFKCPJSEslSZfqeP9WDmTuSYNTxUJJsAKP7UeyCXKatFWvHRdJXoS",
        "disabled": False,
    }
}

app = FastAPI()
conn = UserConnection()

load_dotenv()

SECRET_KEY=os.getenv("SECRET_KEY")
ALGORITHM=os.getenv("ALGORITHM")
stripe.api_key = os.getenv("STRIPE_KEY")

oauth2_scheme = OAuth2PasswordBearer("/token")

class User(BaseModel):
    username: str
    email: str
    full_name: str
    disabled: bool = None

class UserInDB(User):
    hashed_password: str

def get_user(db, username: str):
    if username in db:
        user_data = db[username]
        return UserInDB(**user_data)
    return []

def verify_password(plain_password, hashed_password):
    password_byte_encoded = plain_password.encode('utf-8')
    return checkpw(password_byte_encoded, hashed_password.encode('utf-8'))

def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username", headers={"WWW-Authenticate": "Bearer"})
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect password", headers={"WWW-Authenticate": "Bearer"})
    return user

def create_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, key=SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_current(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, key=SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username)
    if user is None:
        raise credentials_exception
    return user

def get_user_disabled_current(current_user: User = Depends(get_user_current)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

@app.get("/")
def read_root():
    conn
    return {"Hello": "World"}

@app.get("/users/me")
def read_user_me(user: User = Depends(get_user_disabled_current)):
    return user

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    access_token_expire = timedelta(minutes=30)
    access_token_jwt = create_token({"sub": user.username, "exp": datetime.utcnow() + access_token_expire})
    return {"access_token": access_token_jwt, "token_type": "bearer"}

@app.post("/user", status_code=HTTP_201_CREATED)
def insert(user_data: UserSchema):
    data = user_data.model_dump()
    data.pop("id")
    conn.write(data)

@app.get("/users", status_code=HTTP_200_OK)
def read_users():
    items = []
    for item in conn.read_all():
        dictionary = {
            "id": item[0],
            "name": item[1],
            "lastname": item[2],
            "rut": item[3],
            "email": item[4],
            "saldo": item[6]
        }
        items.append(dictionary)
    return items

@app.get("/user/{id}" , status_code=HTTP_200_OK)
def read_user(id: int):
    item = conn.read_one(id)
    if item:
        dictionary = {
            "id": item[0],
            "name": item[1],
            "lastname": item[2],
            "rut": item[3],
            "email": item[4],
            "saldo": item[6]
        }
        return dictionary
    return {"message": "User doesn't exist"}

@app.put("/user/{id}", status_code=HTTP_204_NO_CONTENT)
def update_user(id: int, user_data: UserSchema):
    data = user_data.model_dump()
    data["id"] = id
    conn.update(data)
    return Response(status_code=HTTP_204_NO_CONTENT)

@app.delete("/user/{id}", status_code=HTTP_204_NO_CONTENT)
def delete_user(id: int):
    conn.delete(id)
    return Response(status_code=HTTP_204_NO_CONTENT)

# STRIPE INTEGRATION

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Payment(BaseModel):
    id: str
    amount: int

@app.post('/checkout')
async def create_payment(payment: Payment):
    try:
        print(payment)
        # Create a PaymentIntent with the order amount and currency
        intent = stripe.PaymentIntent.create(
            amount=payment.amount * 100,
            currency='usd',
            payment_method=payment.id,
            confirm=True,
            return_url="http://localhost:3000"
        )
        print("Intent: ", intent)
        return JSONResponse({
            'clientSecret': intent['client_secret']
        })
    except Exception as e:
        print(e)
        return {"error": str(e)}

class PaymentSubscription(BaseModel):
    priceId: str
    paymentId: str

@app.post('/create-subscription')
async def create_subscription(paymentSubscription: PaymentSubscription):
    try:
        print(paymentSubscription)
        # Create a customer
        customer = stripe.Customer.create(
            description="Demo customer",
            payment_method=paymentSubscription.paymentId,
            invoice_settings={
                "default_payment_method": paymentSubscription.paymentId
            }
        )

        customer_id=customer.id

        print(paymentSubscription)
        print(customer)

        # Create a subscription
        subscription = stripe.Subscription.create(
            customer=customer_id,
            collection_method="charge_automatically",
            items=[
                {
                    "price": paymentSubscription.priceId
                }
            ],
            metadata={
                "planId": paymentSubscription.priceId
            },
            payment_settings={
                "payment_method_types": ["card"],
                "save_default_payment_method": "on_subscription"
            },
            expand= ['latest_invoice.payment_intent']
        )

        latest_invoice = subscription.latest_invoice.id

        print(latest_invoice)

        invoice = stripe.Invoice.retrieve(latest_invoice)

        print(invoice)

        payment_intent = invoice.payment_intent

        client_secret = payment_intent.client_secret

        return JSONResponse({
            'clientSecret': client_secret
        })
    except Exception as e:
        return {"error": str(e)}