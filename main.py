# ---------- VIEW С КНОПКАМИ ----------
class FarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Кнопка "подоил"
        self.btn_milk = discord.ui.Button(
            label=f"{'🟢' if is_milked else '🔴'} подоил", 
            style=discord.ButtonStyle.blurple, 
            custom_id="milk_button"
        )
        # Кнопка "покормил"
        self.btn_feed = discord.ui.Button(
            label=f"{'🟢' if is_fed else '🔴'} покормил", 
            style=discord.ButtonStyle.green, 
            custom_id="feed_button"
        )

        self.btn_milk.callback = self.milk_callback
        self.btn_feed.callback = self.feed_callback

        self.add_item(self.btn_milk)
        self.add_item(self.btn_feed)

    async def feed_callback(self, interaction: discord.Interaction):
        global is_fed
        if is_fed:
            # Если уже кормили — пишем "Игрок уже покормил"
            await interaction.response.send_message(f"Игрок {interaction.user.display_name} уже покормил", ephemeral=True)
            return
            
        is_fed = True
        save_state()
        await self.log_click(interaction, "покормил")
        
        # При успехе
        await interaction.response.send_message(f"{interaction.user.display_name}, вы покормили! 🍎", ephemeral=True)

        self.btn_feed.disabled = True
        await self.update_buttons(interaction)
        await reset_timer()

    async def milk_callback(self, interaction: discord.Interaction):
        global is_milked
        if is_milked:
            # Если уже доили — пишем "Игрок уже подоил"
            await interaction.response.send_message(f"Игрок {interaction.user.display_name} уже подоил", ephemeral=True)
            return

        is_milked = True
        save_state()
        await self.log_click(interaction, "подоил")
        
        # При успехе
        await interaction.response.send_message(f"{interaction.user.display_name}, вы подоили! 🥛", ephemeral=True)
        
        self.btn_milk.disabled = True
        await self.update_buttons(interaction)
        await reset_timer()

    async def update_buttons(self, interaction: discord.Interaction):
        global is_fed, is_milked
        
        self.btn_milk.label = f"{'🟢' if is_milked else '🔴'} подоил"
        self.btn_feed.label = f"{'🟢' if is_fed else '🔴'} покормил"
        await interaction.message.edit(view=self)

        if is_fed and is_milked:
            is_fed = False
            is_milked = False
            save_state()

    async def log_click(self, interaction: discord.Interaction, action: str):
        now = datetime.now()
        real_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        rounded_time = current_hour.strftime("%Y-%m-%d %H:00:00")

        entry = {
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "display_name": interaction.user.display_name,
            "action": action,
            "time": real_time,
            "rounded_time": rounded_time,
            "channel_id": interaction.channel_id,
        }
        clicks_log.append(entry)
        save_log()
        print(f"[{entry['rounded_time']}] {entry['user_name']} (ID: {entry['user_id']}) — {action}")
