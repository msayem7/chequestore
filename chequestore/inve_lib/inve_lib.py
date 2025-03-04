import hashlib
import time
import random
from django.utils.text import slugify
import uuid;

def generate_slugify_id():    
    return slugify(generate_alias_id())

def generate_alias_id():
    unique_string = f"{time.time()}{random.randint(0, 1000000)}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:10]
    

#have possibility of collision
def generate_unique_id(): 
    return slugify(str(uuid.uuid4())[:10])