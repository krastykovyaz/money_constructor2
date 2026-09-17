import pandas as pd
from datetime import datetime, timedelta

class Profit:
    def __init__(self, transaction_file):
        self.df_trans = pd.read_excel(transaction_file)


    
    @staticmethod
    def calc_profit_up(table):
        table = table.sort_values(['Дата', 'Время'])

        def collect_profit(df_transactions, flag):
            balance = 0  # Total amount of currency in hand
            wallet = []   # Stores transactions (exchange rate, amount)
            profit = 0    # Total profit calculation

            for _, transaction in df_transactions.iterrows():
                transaction_type = transaction['Тип']
                transaction_amount = transaction[flag]
                transaction_rate = transaction['Курс']

                if transaction_type == 'Пополнение':
                    balance += transaction_amount
                    if transaction_rate != '-':
                        wallet.append([transaction_rate, transaction_amount])

                elif transaction_type == 'Изъятие':
                    balance -= abs(transaction_amount)

                elif transaction_type == 'Обмен':
                    if transaction_amount > 0:
                        # Buying currency (adding to wallet)
                        balance += transaction_amount
                        wallet.append([transaction_rate, transaction_amount])

                    elif transaction_amount < 0 and balance >= abs(transaction_amount):
                        # Selling currency (profit calculation)
                        remaining_amount = abs(transaction_amount)
                        new_wallet = []
                        # print('1', wallet, profit)
                        for rate, amount in wallet:
                            if remaining_amount == 0:
                                new_wallet.append([rate, amount])
                                continue

                            if amount >= remaining_amount:
                                profit += (transaction_rate - rate) * remaining_amount
                                amount -= remaining_amount
                                remaining_amount = 0
                                if amount > 0:
                                    new_wallet.append([rate, amount])
                            else:
                                profit += (transaction_rate - rate) * amount
                                remaining_amount -= amount
                        # print('2', wallet, profit)
                        wallet = new_wallet
                        balance -= abs(transaction_amount)

            return profit

        # Calculate profit for each currency type
        blue_dollar_profit = collect_profit(table, 'Синий доллар')
        green_dollar_profit = collect_profit(table, 'Зеленый доллар')
        euro_profit = collect_profit(table, 'Евро')

        return blue_dollar_profit + green_dollar_profit + euro_profit
    
    @staticmethod
    def calc_profit_down(table):
        table = table.sort_values(['Дата', 'Время'])

        def collect_profit(df_transactions, flag):
            balance = 0
            transactions = []
            profit = 0

            for _, desk in df_transactions.iterrows():
                transaction_type = desk['Тип']
                transaction_amount = desk[flag]
                transaction_rate = desk['Курс']

                if transaction_type == 'Пополнение':
                    balance += transaction_amount

                elif transaction_type == 'Изъятие':
                    balance -= abs(transaction_amount)

                elif transaction_type == 'Обмен' and transaction_amount < 0:
                    # Currency borrowed (added to transaction history)
                    balance -= abs(transaction_amount)
                    transactions.append([transaction_rate, transaction_amount])

                elif transaction_type == 'Обмен' and transaction_amount > 0:
                    # Currency repaid (profit calculation)
                    balance += transaction_amount
                    remaining_transaction = transaction_amount
                    new_transactions = []

                    for rate, amount in transactions:
                        if remaining_transaction == 0:
                            new_transactions.append([rate, amount])
                            continue

                        if abs(amount) <= remaining_transaction:
                            profit += (abs(rate) - abs(transaction_rate)) * abs(amount)
                            remaining_transaction -= abs(amount)
                        else:
                            profit += (abs(rate) - abs(transaction_rate)) * remaining_transaction
                            new_transactions.append([rate, amount + remaining_transaction])
                            remaining_transaction = 0

                    transactions = new_transactions

            return profit

        # Compute profit for blue dollar loans
        blue_dollar_profit = collect_profit(table, 'Синий доллар займ')

        green_dollar_profit = collect_profit(table,\
                                  'Зеленый доллар займ')
        euro_profit = collect_profit(table,\
                                  'Евро займ')
        return blue_dollar_profit + green_dollar_profit + euro_profit

        
    def calc_day(self, focus_date=None):
        current_date = datetime.now().date().strftime("%Y-%m-%d")
        if focus_date:
            current_date = focus_date
        # prev_date = (datetime.now().date() - timedelta(1)).strftime("%Y-%m-%d")
        down = self.calc_profit_down((
            self.df_trans
            # .query(f"(Дата in ['{current_date}'])")
            .sort_values(['Дата', 'Время'])
            )) - self.calc_profit_down((
                self.df_trans
                .query(f"(Дата not in ['{current_date}'])")
                .sort_values(['Дата', 'Время'])
            ))
        up = self.calc_profit_up((
            self.df_trans
            # .query(f"(Дата in ['{current_date}'])")
            .sort_values(['Дата', 'Время'])
        )) - self.calc_profit_up((
            self.df_trans
            .query(f"(Дата not in ['{current_date}'])")
            .sort_values(['Дата', 'Время'])
        ))
        return int(abs(up + down))
    
    def calc_week(self):
        days = []
        for i in range(7):
            days.append((datetime.now().date() - timedelta(i)).strftime("%Y-%m-%d"))
        # print(days)
        down = self.calc_profit_down((
            self.df_trans
            # .query(f"(Дата in {days})")
            .sort_values(['Дата', 'Время'])
            )) - self.calc_profit_down((
                self.df_trans
                .query(f"(Дата not in {days})")
                .sort_values(['Дата', 'Время'])
            ))
        up = self.calc_profit_up((
            self.df_trans
            # .query(f"(Дата in {days})")
            .sort_values(['Дата', 'Время'])
        )) - self.calc_profit_up((
            self.df_trans
            .query(f"(Дата not in {days})")
            .sort_values(['Дата', 'Время'])
        ))
        return int(abs(up + down))
    
    def calc_month(self):
        # current_date = datetime.now().date().strftime("%Y-%m-%d")
        days = []
        for i in range(30):
            days.append((datetime.now().date() - timedelta(i)).strftime("%Y-%m-%d"))
        # print(days)
        down = self.calc_profit_down((
            self.df_trans
            .query(f"(Дата in {days})")
            .sort_values(['Дата', 'Время'])
            )) - self.calc_profit_down((
                self.df_trans
                .query(f"(Дата not in {days})")
                .sort_values(['Дата', 'Время'])
            ))
        up = self.calc_profit_up((
            self.df_trans
            .query(f"(Дата in {days})")
            .sort_values(['Дата', 'Время'])
        )) - self.calc_profit_up((
            self.df_trans
            .query(f"(Дата not in {days})")
            .sort_values(['Дата', 'Время'])
        ))
        return int(abs(up + down))

    def get_current_transaction(self, flag):
        if flag =='up':
            out = self.calc_profit_up((
            self.df_trans
           
            .sort_values(['Дата', 'Время'])
            )) - self.calc_profit_up((
                self.df_trans
               
                .sort_values(['Дата', 'Время'])
            ).iloc[:-1,:])
            return int(out)
        elif flag =='down':
            out = self.calc_profit_down((
            self.df_trans
           
            .sort_values(['Дата', 'Время'])
            )) - self.calc_profit_down((
                self.df_trans
               
                .sort_values(['Дата', 'Время'])
            ).iloc[:-1,:])
            return int(out)


        
    def calc_all_days(self):
        down = self.calc_profit_down((
            self.df_trans
            .sort_values(['Дата', 'Время'])
            ))
        up = self.calc_profit_up((
            self.df_trans
            .sort_values(['Дата', 'Время'])
        ))
        return int(abs(up + down))
    
    @staticmethod
    def eval_loan(df_, currency):
        df_type = df_.query(f"Тип in ['Пополнение', 'Изъятие']")
        need = df_[currency].sum().item() - df_type[currency].sum().item()
        return need
    
    def get_profit(self, flag, is_loan):
        if flag == 'transaction' and is_loan != False:
            residual = self.eval_loan(self.df_trans, is_loan)
            # print(residual)
            if is_loan and residual < 0:
                return f"Нужно вернуть {is_loan} в размере: {residual}, затем расчитаю профит"
            else:
                return self.get_current_transaction('down')
        elif flag == 'transaction' and is_loan == False:
            return self.get_current_transaction('up')
        elif flag == 'day':
            return self.calc_day()
        elif flag == 'week':
            return self.calc_week()
        elif flag == 'month':
            return self.calc_month()
        elif flag == 'all_days':
            return self.calc_all_days()
            

if __name__=='__main__':
    TRANSACTIONS_FILE = "transactions2.xlsx"
    prof = Profit(TRANSACTIONS_FILE)
    print(prof.get_profit('transaction', False))
