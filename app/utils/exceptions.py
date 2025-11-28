from fastapi import HTTPException, status, Request


class FridgeNotFoundException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fridge not found or access denied",
        )


class FridgeNotFoundError(Exception):
    def __init__(self, fridge_id: int):
        self.fridge_id = fridge_id


class ProductNotFoundException(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )


class InsufficientQuantityException(HTTPException):
    def __init__(self, available: float, unit: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient quantity. Available: {available} {unit}",
        )


class DietaryRestrictionViolationException(HTTPException):
    def __init__(self, restriction: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recipe violates dietary restriction: {restriction}",
        )
