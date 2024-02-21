import os
import stripe
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

app = FastAPI()

load_dotenv()

stripe.api_key = os.getenv("STRIPE_KEY")

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

### SUBSCRIPTION STRIPE

class PaymentSubscription(BaseModel):
    priceId: str
    paymentId: str

@app.post('/create-subscription')
async def create_subscription(paymentSubscription: PaymentSubscription):
    try:
        
        # Create a customer
        customer = stripe.Customer.create(
            description="Demo customer",
            payment_method=paymentSubscription.paymentId,
            invoice_settings={
                "default_payment_method": paymentSubscription.paymentId
            }
        )

        # Create a subscription
        subscription = stripe.Subscription.create(
            customer=customer.id,
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

        invoice = stripe.Invoice.retrieve(latest_invoice)

        print(invoice)

        return JSONResponse({
            'status': invoice.status
        })
    except Exception as e:
        return {"error": str(e)}

### CREATE PRODUCT STRIPE

class Product(BaseModel):
    name: str

@app.post('/create-product')
async def create_product(new_product: Product):
    try:
        product = stripe.Product.create(
            name= new_product.name
        )
        return JSONResponse({
            'productId': product.id
        })
    except Exception as e:
        return {"error": str(e)}

### CREATE PRICE STRIPE

class Price(BaseModel):
    productId: str
    amount: int
    currency: str
    is_recurring: bool
    interval: str
    interval_count: int

@app.post('/create-price')
async def create_price(new_price: Price):
    try:
        if new_price.is_recurring:
            price = stripe.Price.create(
                product=new_price.productId,
                unit_amount=new_price.amount * 100,
                currency=new_price.currency,
                recurring={
                    "interval": new_price.interval,
                    "interval_count": new_price.interval_count
                }
            )
        else:
            price = stripe.Price.create(
                product=new_price.productId,
                unit_amount=new_price.amount * 100,
                currency=new_price.currency
            )
        return JSONResponse({
            'priceId': price.id
        })
    except Exception as e:
        return {"error": str(e)}
    
### CREATE CUSTOMER STRIPE

class Customer(BaseModel):
    email: str

@app.post('/create-customer')
async def create_customer(new_customer: Customer):
    try:
        customer = stripe.Customer.create(
            email=new_customer.email
        )
        return JSONResponse({
            'customerId': customer.id
        })
    except Exception as e:
        return {"error": str(e)}
    
### CREATE PAYMENT METHOD STRIPE
    
class PaymentMethod(BaseModel):
    customerId: str
    card: dict

@app.post('/create-payment-method')
async def create_payment_method(new_payment_method: PaymentMethod):
    try:
        payment_method = stripe.PaymentMethod.create(
            type="card",
            card=new_payment_method.card
        )

        attached_payment_method = stripe.PaymentMethod.attach(
            payment_method.id,
            customer=new_payment_method.customerId
        )

        return JSONResponse({
            'paymentId': attached_payment_method.id
        })
    except Exception as e:
        return {"error": str(e)}
