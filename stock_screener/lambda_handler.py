"""
AWS Lambda handler for stock screener
"""
import json
from screener import StockScreener


def lambda_handler(event, context):
    """
    AWS Lambda entry point
    """
    try:
        print("Starting stock screener Lambda function...")

        screener = StockScreener()
        screener.run()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Stock screener executed successfully'
            })
        }
    except Exception as e:
        print(f"Error in Lambda function: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error: {str(e)}'
            })
        }
