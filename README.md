# NotPX Bot ⬛

Automated script for NotPixelBot with painting on the template, passing in-game proof-of-humanity checks and more

## Requirements

[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3670A0?style=flat&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D20.18.0-6DA55F?style=flat&logo=node.js&logoColor=white)](https://nodejs.org/)

## Features  

<table>
  <thead>
    <tr>
      <th>Feature</th>
      <th>Supported</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>SuperMegaCool Capybara intro included</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Passing in-game proof-of-humanity checks</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>NotPX API change detection</td>
      <td><img src="https://img.shields.io/badge/TODO-in%20progress-green" alt="TODO badge"></td>
    </tr>
    <tr>
      <td>Packaged .exe file</td>
      <td><img src="https://img.shields.io/badge/TODO-in%20progress-green" alt="TODO badge"></td>
    </tr>
    <tr>
      <td>Proxy binding to session</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>User-Agent binding to session</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Auto-detect new .session and register it in bot</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Auto-paiting</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Auto-tasks</td>
      <td><img src="https://img.shields.io/badge/TODO-in%20progress-green" alt="TODO badge"></td>
    </tr>
    <tr>
      <td>Auto-use bombs</td>
      <td><img src="https://img.shields.io/badge/TODO-in%20progress-green" alt="TODO badge"></td>
    </tr>
    <tr>
      <td>Auto-claim px</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Auto-upgrade boosters</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Night sleep mode</td>
      <td>✅</td>
    </tr>
    <tr>
      <td>Async working</td>
      <td>✅</td>
    </tr>
  </tbody>
</table>

## Why are we better than the rest of the public scripts?

### ✨ Capybara Intro (game changer, killer feature)

![Capybara Intro](https://github.com/Dellenoam/NotPixelBot/tree/master/assets/Capybara_Intro.gif)

### 📝 Shortly about in-game events check

We are passing proof-of-humanity checks with a real task solution instead of using random responses like other public scripts do.

### 📊 Detailed about in-game events check

In the game, there are several types of events, which are collectively referred to as **proof-of-humanity events**. And our script is passing them with a real task solution instead of using random responses like other public scripts do.

    🔹 TGAalytics Events: These events occur in various situations, but primarily when a player logs into the game. When a player successfully enters the game, a tganalytics event is triggered, sending a signal to the server indicating that the login was successful.
    🔹 Plausible Events: These events is sent every time the player performs an in-game action. For example, it can be triggered when a player enters a shop to make purchases or decides to change the paint template.

The key aspect of plausible events is that they automatically send an event containing a reference to the location the player has navigated to. For instance, if the player enters a shop, the event will include:

    🔹 A link to that shop
    🔹 The type of event
    🔹 The base URL from which the action originated

In contrast, tganalytics events have specific requirements. These events necessitate the completion of a task or challenge, which the player must solve in order to generate a valid response that is then sent back to the server. Unlike plausible events, which occur passively, tganalytics events demand in-game scripts to meet the conditions for the event to be registered.

### ⚠️ Again about in-game events check

Passing these checks with a real solution is important, as the project can shave you on this point, so using our script you slightly but secure yourself from this incident

### 📝 Shortly about auto-painting

Our script can paint on the canvas using real-time updated data instead of random pixels like the rest of the public scripts. This means that you will typically receive PX for painting, provided that no one has changed the color of that pixel during that time.

### 📊 Detailed about auto-painting

The game retrieves the canvas through an API and then initiates a WebSocket connection to update it. Once the connection is established, the game decodes the incoming data and utilizes this information to refresh the template. Our script fully implements this functionality, ensuring that your canvas is always up to date.
For pixel painting, we employ an algorithm that identifies pixels on the canvas that have different colors compared to the template. As soon as such a pixel is detected, we send a request to paint it. This means that you will almost always receive PX for painting according to the template on the canvas.
However, there are instances when the painting process may fail. This can occur if the script does not manage to paint the pixel before another user does, which can happen even with a real person. Thus, while our script optimizes the painting process, occasional delays may lead to missed opportunities for painting specific pixels.

### ⚠️ Again about auto-painting

Most scripts rely on random pixel painting, which can be easily detected by the game. This method not only increases the likelihood of being flagged by game but also means that you will not receive any PX, as any painting outside of the template will give you 0 PX.

#### 🚩 Risks of Alternative Methods

Additionally, if you utilize different methods for identifying pixels, such as:

    Using pixel information via the API
    Retrieving the canvas via the API before each painting action

These practices can also have negative implications. The game may scrutinize your activity more closely, leading to potential penalties or bans.

#### 🌟 Our Solution

Our script addresses these issues, offering a slight improvement in your situation. By focusing on legitimate pixel painting strategies that align with the game's mechanics, you can enhance your chances of successfully earning PX while minimizing the risk of detection.

### 🔗 We have a clear use of referrals

If you use change referral id to your own in the settings, it will be. Our script does not prevent you from doing this, unlike some public scripts.

## [Settings](https://github.com/Dellenoam/NotPixelBot/blob/master/.env-example)

<table>
  <thead>
    <tr>
      <th>Settings</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>API_ID / API_HASH</td>
      <td>API credentials for Telegram API</td>
    </tr>
    <tr>
      <td>PLAY_INTRO</td>
      <td>True/False playing intro on script start (DON'T YOU DARE TO TURN THIS OFF)</td>
    </tr>
    <tr>
      <td>INITIAL_START_DELAY_SECONDS</td>
      <td>Delay range in seconds to use for a random delay when starting the session</td>
    </tr>
    <tr>
      <td>ITERATION_SLEEP_MINUTES</td>
      <td>How long the script will wait before starting the next iteration of the script (painting, claiming and e.t.c)</td>
    </tr>
    <tr>
      <td>USE_REF</td>
      <td>True/False the use of a referral to start the bot</td>
    </tr>
    <tr>
      <td>REF_ID</td>
      <td>Referral ID to be used</td>
    </tr>
    <tr>
      <td>SLEEP_AT_NIGHT</td>
      <td>True/False sleep at night</td>
    </tr>
    <tr>
      <td>NIGHT_START_HOURS</td>
      <td>Start hours range of the night</td>
    </tr>
    <tr>
      <td>NIGHT_END_HOURS</td>
      <td>End hours range of the night</td>
    </tr>
    <tr>
      <td>ADDITIONAL_NIGHT_SLEEP_MINUTES</td>
      <td>Additional minutes range to sleep at night</td>
    </tr>
    <tr>
      <td>CLAIM_PX</td>
      <td>True/False auto-claim px</td>
    </tr>
    <tr>
      <td>UPGRADE_BOOSTS</td>
      <td>True/False auto-upgrade boosters</td>
    </tr>
    <tr>
      <td>PAINT_PIXELS</td>
      <td>True/False auto-painting</td>
    </tr>
  </tbody>
</table>

## How to start 📚

Before you begin, make sure you have meet the [requirements](#requirements)

## Obtaining API Keys

1. Go to my.telegram.org and log in using your phone number.
2. Select "API development tools" and fill out the form to register a new application.
3. Record the API_ID and API_HASH provided after registering your application in the .env file.

Sometimes when creating a new application, it may display an error. It is still not clear what causes this, but you can try the solutions described on [stackoverflow](https://stackoverflow.com/questions/68965496/my-telegram-org-sends-an-error-when-i-want-to-create-an-api-id-hash-in-api-devel).

## Linux manual installation

```shell
python3 -m venv .venv
source venv/bin/activate
pip3 install poetry
poetry install --only main
cp .env-example .env
nano .env  # Specify your API_ID and API_HASH, the rest is taken by default
python3 main.py
```

## Windows manual installation

```shell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env-example .env  # Specify your API_ID and API_HASH, the rest is taken by default
```

## Run the script

![NotPixel Intro](https://github.com/Dellenoam/NotPixelBot/tree/master/assets/NotPixel_Intro.gif)

You can run the script with `python3 main.py` if you are inside the `NotPixelBot` folder

Also, you can use flag `--action` or `-a` to quickly run the script with specified action.

```shell
~/NotPixelBot >>> python3 main.py --action [1/2]
# Or
~/NotPixelBot >>> python3 main.py -a [1/2]
```

Where [1/2] is:

    1 - Creates a session
    2 - Run bot

So for example if you want to create a session, you can run this command:

```shell
~/NotPixelBot >>> python3 main.py -a 1
```

## Contacts

If you have any questions or suggestions, please feel free to contact us in comments.

[![Capybara Society Telegram Channel](https://img.shields.io/badge/Capybara%20Society-Join-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/capybara_society)
