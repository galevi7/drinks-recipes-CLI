from collections import deque

import boto3
import requests
import time
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
import json
from botocore.exceptions import ClientError


def print_recipe(recipe):

    name = recipe.get('Name')
    category = recipe.get('Category')
    description = recipe.get('Description')
    ingredients = recipe.get('Ingredients')
    added_at = recipe.get('Added_At', None)

    print(f"Recipe name: {name}")
    print(f"Category: {category}")
    print(f"Description: {description}")
    print(f"Ingredients:")
    for ingredient, description in ingredients.items():
        print(f"{ingredient}: {description}")

    if added_at:
        print(f"Added_At: {added_at}")
    print("\n")


def main(server_url):

    with open("cache.json", "r") as f:
        last_search = deque(json.load(f))

    while True:
        print("1. Fetch a recipe by name (exact name!!!)")
        print("2. Get last recipe(s) searched")
        print("3. Get a Random recipe")
        print("4. Delete a recipe")
        print("5. Get all your beer recipes")
        print("6. Get all your cocktail recipes")
        print("7. exit \n")

        choice = input("Please enter your choice (1-7) \n")

        try:
            choice = int(choice)
            if choice < 0 or choice > 6:
                print("Please enter a valid number! \n")
                time.sleep(1)
                continue

        except ValueError:
            print("Invalid input! Please enter a number between 1-6.\n")
            time.sleep(1)
            continue

        match choice:

            ### Getting a recipe by name
            case 1:
                recipe_name = input("Enter the recipe name: \n")
                recipe = None
                print("Fetching recipe by name...")

                for recipe_, recipe_json in last_search:
                    if recipe_ == recipe_name:
                        recipe = recipe_json

                if not recipe and not get_recipe(recipe_name):
                    params = {
                        "name": recipe_name
                    }
                    response = requests.get(server_url + "recipe", params=params)
                    if response.status_code == 200:
                        recipe = response.json()

                    elif response.status_code == 404:
                        print(response.text)

                if recipe:
                    if (recipe_name, recipe) not in last_search:
                        if len(last_search) == 5:
                            last_search.popleft()
                        last_search.append((recipe_name, recipe))

                    name = recipe.get('Name')
                    category = recipe.get('Category')
                    description = recipe.get('Description')
                    ingredients = recipe.get('Ingredients')

                    print_recipe(recipe)


                    save = input("Do you want to save this recipe? (Enter Y as a yes) \n")
                    if save.lower() == 'y':
                        print(add_record_to_table(name, description, ingredients, category))


            ### Getting last searched recipes
            case 2:
                print("Fetching last recipe(s)...")
                while True:
                    num = input("Enter the number of last recipes to fetch (1-5), or press 'q' to quit: ")

                    if num.lower() == 'q':
                        break

                    if num.isdigit() and 1 <= int(num) <= 5:
                        num = int(num)
                        break
                    else:
                        print("Invalid input! Please enter a number between 1 and 5.")

                for i in range(len(last_search)-1, len(last_search)-1-min(len(last_search), num), -1):
                    print_recipe(last_search[i][1])


            ### Getting a random recipe
            case 3:
                print("Fetching a random recipe...")
                while True:
                    choice = input("Choose category (press 1 or 2) \n 1. Beer \n 2. Cocktail \n")
                    try:
                        choice = int(choice)
                        if choice !=1 and choice != 2:
                            print("Press 1 or 2 only!!!!!!")
                        else:
                            if choice == 1:
                                category = "Beer"
                            else:
                                category = "Cocktail"
                            break
                    except ValueError as e:
                        print("Press 1 or 2 only!!!!!!")

                params={
                    "category": category
                }

                response = requests.get(server_url + "random", params=params)

                if response.status_code == 200:
                    print_recipe(response.json())
                else:
                    print("There's problem with the server.")

            ### Delete a recipe
            case 4:
                recipe_name = input("Enter the recipe name: \n")
                while True:
                    choice = input("Choose category (press 1 or 2) \n 1. Beer \n 2. Cocktail \n")
                    try:
                        choice = int(choice)
                        if choice != 1 and choice != 2:
                            print("Press 1 or 2 only!!!!!!")
                        else:
                            if choice == 1:
                                category = "Beer"
                            else:
                                category = "Cocktail"
                            break
                    except ValueError as e:
                        print("Press 1 or 2 only!!!!!!")

                print("Deleting the recipe...")
                print(delete_record_from_table(recipe_name, category))

            #### Fetching all Beer recipes
            case 5:
                print("Fetching all beer recipes... \n")
                response = get_category_recipes("Beer")
                if not response:
                    print("You don't have any cocktails recipes!!!")
                else:
                    for beer_recipe in response:
                        print_recipe(beer_recipe)

            #### Fetching all cocktail recipes
            case 6:
                print("Fetching all cocktail recipes... \n")
                response = get_category_recipes("Cocktail")
                if not response:
                    print("You don't have any cocktails recipes!!!")
                else:
                    for cocktail_recipe in response:
                        print_recipe(cocktail_recipe)

            ### Exit program
            case 7:
                print("Exiting program...")
                return

        ### saving last searched recipes for cache use
        data_to_save = list(last_search)
        with open("cache.json", "w") as f:
            json.dump(data_to_save, f, indent=4)
        time.sleep(2)


def create_table(table_name, partition_key, sort_key=None, region='us-east-2'):
    dynamodb = boto3.resource('dynamodb', region_name=region)

    key_schema = [{'AttributeName': partition_key, 'KeyType': 'HASH'}]
    attribute_definitions = [{'AttributeName': partition_key, 'AttributeType': 'S'}]  # Default type as 'S'

    if sort_key:
        key_schema.append({'AttributeName': sort_key, 'KeyType': 'RANGE'})
        attribute_definitions.append({'AttributeName': sort_key, 'AttributeType': 'S'})  # Default type as 'S'

    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=key_schema,
        AttributeDefinitions=attribute_definitions,
        ProvisionedThroughput={
            'ReadCapacityUnits': 10,
            'WriteCapacityUnits': 10
        }
    )

    print(f"Creating table '{table_name}'...")
    table.wait_until_exists()
    print(f"Table '{table_name}' is now active!")

    return table


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


if __name__ == "__main__":

    main("http://localhost:5000/")







