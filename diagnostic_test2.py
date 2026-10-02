import sys
print("Python :", sys.version)

print("1/5 - import flask ...")
from flask import Flask
print("    OK")

print("2/5 - import flask_sqlalchemy ...")
from flask_sqlalchemy import SQLAlchemy
print("    OK")

print("3/5 - import flask_login ...")
from flask_login import LoginManager
print("    OK")

print("4/5 - import flask_wtf ...")
from flask_wtf import CSRFProtect
print("    OK")

print("5/5 - import werkzeug.security ...")
from werkzeug.security import generate_password_hash
print("    OK")

print("")
print("TOUT EST OK")
