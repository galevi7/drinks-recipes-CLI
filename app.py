from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from flask import Flask, request, jsonify
import json
import requests
from datetime import datetime
import boto3

app = Flask(__name__)

# constants
cocktails_api = "https://www.thecocktaildb.com/api/json/v1/1/"
beers_api = "https://punkapi.online/v3/beers"


### functions for actions with DynamoDB


def add_record_to_table(name, description, ingredients, category, table_name="Gal_Bar", region='us-east-2'):
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    if not name or not category:
        return "Not valid name or category!"

    item = {
        "Name": name.lower(),
        "Description": description,
        "Ingredients": json.dumps(ingredients),  # Convert to JSON string if needed
        "Category": category,
        "Added_At": datetime.utcnow().isoformat()
    }

    try:
        response = table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(#N) AND attribute_not_exists(Category)",
            ExpressionAttributeNames={
                "#N": "Name"
            }
        )
        return "Recipe was added!"

    except ClientError as e:
        if e.response['Error']['Code'] == "ConditionalCheckFailedException":
            return "Recipe already in the DB!"
        else:
            return f"Error: {e.response['Error']['Message']}"


def delete_record_from_table(name, category, table_name="Gal_Bar", region='us-east-2'):
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    response = table.delete_item(
        Key={
            'Name': name.lower(),
            'Category': category
        },
        ReturnValues="ALL_OLD"
    )


    if 'Attributes' in response:
        return "Recipe was deleted!"

    return "Recipe does not exist!"


def get_recipe(name, table_name="Gal_Bar", region='us-east-2'):
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    response = table.query(
        KeyConditionExpression=Key('Name').eq(name)
    )

    return response['Items'][0] if len(response['Items']) > 0 in response else None


def get_category_recipes(category, table_name="Gal_Bar", region='us-east-2'):
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    response = table.scan(
        FilterExpression=Attr('Category').eq(category)
    )

    recipes = sorted(response['Items'], key=lambda x: x['Added_At'])

    for recipe in recipes:
        recipe["Ingredients"] = json.loads(recipe["Ingredients"])

    return recipes if len(response["Items"]) > 0 else None


### functions for unify jsons to single format

def beer_json_to_format(beer_response):
    beer_dict = beer_response
    name = beer_dict["name"]
    description = beer_dict['description']
    ingredients = {}
    ingredients_dict = beer_dict['ingredients']

    malts = ingredients_dict["malt"]
    for malt_dict in malts:
        ingredients[malt_dict["name"]] = str(malt_dict["amount"]["value"]) + " " + malt_dict["amount"]["unit"]

    hops = ingredients_dict["hops"]
    for hop_dict in hops:
        ingredients[hop_dict["name"]] = str(hop_dict["amount"]["value"]) + " " + hop_dict["amount"]["unit"] + \
                                        " add in " + hop_dict["add"] + " for " + hop_dict["attribute"]
    ingredients["yeast"] = ingredients_dict["yeast"]

    category = "Beer"

    return jsonify({
        "Name": name,
        "Description": description,
        "Ingredients": ingredients,
        "Category": category,
    }), 200


def cocktail_json_to_format(cocktail_response, recipe_name=None):
    cocktail_list = cocktail_response["drinks"]
    cocktail_dict = {}
    if recipe_name:
        for cocktail in cocktail_list:
            if cocktail["strDrink"].lower() == recipe_name.lower():
                cocktail_dict = cocktail
                break
    else:
        if cocktail_list:
            cocktail_dict = cocktail_list[0]

    if not cocktail_dict:
        return "No such recipe!", 404

    name = cocktail_dict["strDrink"]
    description = cocktail_dict['strInstructions']
    ingredients = {}

    for i in range(1, 16):
        ingredient = cocktail_dict.get("strIngredient" + str(i), None)
        if ingredient:
            ingredients[ingredient] = cocktail_dict.get("strMeasure" + str(i))
        else:
            break

    category = "Cocktail"


    return jsonify({
        "Name": name,
        "Description": description,
        "Ingredients": ingredients,
        "Category": category,
    }), 200


# routes to the client requests


### check if the server alive
@app.route('/alive', methods=['GET'])
def alive():
    return "ALIVE!", 200


@app.route('/recipe', methods=['GET', 'POST', 'DELETE'])
def recipe():
    recipe_name = request.args.get('name')
    if request.method == 'GET':

        db_response = get_recipe(recipe_name)
        if db_response:
            return db_response, 200

        beer_response = requests.get(beers_api + f"?beer_name={recipe_name}&page= 1").json()
        cocktail_response = requests.get(cocktails_api + f"search.php?s={recipe_name}").json()

        is_beer = len(beer_response) > 0
        is_cocktail = cocktail_response["drinks"] is not None

        if not is_beer and not is_cocktail:
            return "No such recipe!", 404

        if is_beer:
            return beer_json_to_format(beer_response[0])

        else:
            return cocktail_json_to_format(cocktail_response, recipe_name)

    elif request.method == 'POST':
        args = request.args
        return add_record_to_table(recipe_name, args.get('description'), args.get('ingredients'), args.get('category'))

    else:
        return delete_record_from_table(recipe_name, request.args['category'])


@app.route('/random', methods=['GET'])
def random():
    category = request.args.get("category")

    if category == "Beer":
        response = requests.get(beers_api + "/random").json()
        return beer_json_to_format(response)

    else:
        response = requests.get(cocktails_api + "random.php").json()
        return cocktail_json_to_format(response)


@app.route('/category', methods=['GET'])
def get_category():
    category = request.args.get("category")

    recipes = get_category_recipes(category)
    if recipes:
        return recipes, 200

    else:
        return f"You haven't saved any recipes of {category} yet!", 404


if __name__ == '__main__':
    app.run()
