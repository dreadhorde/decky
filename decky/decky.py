import os, sqlite3, sass, json, smartypants, re, time

from html.parser import HTMLParser
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, Markup, jsonify, Response
from sassutils.wsgi import SassMiddleware
from datetime import datetime
from math import ceil
from random import randint
from titlecase import titlecase
from werkzeug.security import generate_password_hash, check_password_hash
import flask_login

app = Flask(__name__)
app.config.from_object(__name__)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)

app.wsgi_app = SassMiddleware(
    app.wsgi_app, {'decky': ('static/sass', 'static/css', '/static/css')})

app.config.update(
    dict(
        DEBUG = True,
        DATABASE=os.path.join(app.root_path, 'decky.db'),
        SECRET_KEY='development key',
        USERNAME='admin',
        PASSWORD='default'))

print(app.root_path)

@login_manager.user_loader
def load_user(user_id):
    print(User.get(user_id))
    return User.get(user_id)

class user(flask_login.UserMixin):
    id = 'bradforddjohnson@gmail.com',
    name = 'CakeSphere'

current_user = user()

# Default number of items per page for paginated content
PER_PAGE = 45

# All Magic: The Gathering Ability Words for use on cards
ABILITY_WORDS = [
    "Battalion", "Bloodrush", "Channel", "Chroma", "Cohort", "Constellation",
    "Converge", "Council\'s dilemma", "Delirium", "Domain", "Fateful hour",
    "Ferocious", "Formidable", "Grandeur", "Hellbent", "Heroic", "Imprint",
    "Inspired", "Join forces", "Kinship", "Landfall", "Lieutenant",
    "Metalcraft", "Morbid", "Parley", "Radiance", "Raid", "Rally", "Revolt",
    "Spell mastery", "Strive", "Sweep", "Tempting offer", "Threshold",
    "Will of the council", "Eminence"
]

# All Magic: The Gathering Keyword Abilities for use on cards
KEYWORD_ABILITIES = [
    "Deathtouch", "Defender", "Double Strike", "Enchant", "Equip",
    "First Strike", "Flash", "Flying", "Haste", "Hexproof", "Indestructible",
    "Intimidate", "Landwalk", "Lifelink", "Protection", "Reach", "Shroud",
    "Trample", "Vigilance", "Banding", "Rampage", "Cumulative Upkeep",
    "Flanking", "Phasing", "Buyback", "Shadow", "Cycling", "Echo",
    "Horsemanship", "Fading", "Kicker", "Flashback", "Madness", "Fear",
    "Morph", "Amplify", "Provoke", "Storm", "Affinity", "Entwine", "Modular",
    "Sunburst", "Bushido", "Soulshift", "Splice", "Offering", "Ninjutsu",
    "Epic", "Convoke", "Dredge", "Transmute", "Bloodthirst", "Haunt",
    "Replicate", "Forecast", "Graft", "Recover", "Ripple", "Split Second",
    "Suspend", "Vanishing", "Absorb", "Aura Swap", "Delve", "Fortify",
    "Frenzy", "Gravestorm", "Poisonous", "Transfigure", "Champion",
    "Changeling", "Evoke", "Hideaway", "Prowl", "Reinforce", "Conspire",
    "Persist", "Wither", "Retrace", "Devour", "Exalted", "Unearth", "Cascade",
    "Annihilator", "Level Up", "Rebound", "Totem Armor", "Infect",
    "Battle Cry", "Living Weapon", "Undying", "Miracle", "Soulbond",
    "Overload", "Scavenge", "Unleash", "Cipher", "Evolve", "Extort", "Fuse",
    "Bestow", "Tribute", "Dethrone", "Hidden Agenda", "Outlast", "Prowess",
    "Dash", "Exploit", "Menace", "Renown", "Awaken", "Devoid", "Ingest",
    "Myriad", "Surge", "Skulk", "Emerge", "Escalate", "Melee", "Crew",
    "Fabricate", "Partner", "Undaunted", "Improvise", "Aftermath", "Embalm",
    "Eternalize", "Afflict"
]

# Supported Magic: The Gathering formats
FORMATS = [
    "Standard", "Modern", "Legacy", "Vintage", "Block Constructed",
    "Sealed Deck", "Booster Draft", "Rochester Draft", "Cube Draft",
    "Two-Headed Giant", "Pauper", "Peasant", "Frontier", "Rainbow Stairwell",
    "Singleton", "Tribal Wars", "Back Draft", "Reject Rare Draft", "Type 4",
    "Free-For-All", "Star", "Assassin", "Emperor", "Vanguard", "Planar Magic",
    "Archenemy", "Commander", "Brawl"
]

# All basic Card types in Magic: The Gathering
CARD_TYPES = [
    "Land", "Creature", "Artifact", "Enchantment", "Planeswalker", "Instant",
    "Sorcery", "Tribal"
]

PATH_TO_JSON = app.root_path + '/static/json'

app.config.from_envvar('DECKY_SETTINGS', silent=True)


def connect_db():
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def get_db():
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


class Pagination(object):
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def iter_pages(self,
                   left_edge=1,
                   left_current=1,
                   right_current=1,
                   right_edge=1):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
             (num > self.page - left_current - 1 and \
             num < self.page + right_current) or \
             num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def url_for_other_page(page):
    args = request.view_args.copy()
    args['page'] = page
    return url_for(request.endpoint, **args)


app.jinja_env.globals['url_for_other_page'] = url_for_other_page


def format_set(raw_set):
    out_set = {}
    fields = {
     "baseSetSize", \
     "block", \
     "boosterV3", \
     "code", \
     "codeV3", \
     "isFoilOnly", \
     "isOnlineOnly", \
     "keyruneCode", \
     "mcmName", \
     "mcmId", \
     "meta", \
     "mtgoCode", \
     "name", \
     "parentCode", \
     "releaseDate", \
     "tcgplayerGroupId", \
     "tokens", \
     "totalSetSize", \
     "translations", \
     "type", \
     "cards" }
    for field in fields:
        if field in raw_set:
            out_set[field] = raw_set[field]
        else:
            out_set[field] = ""
    return out_set


def format_card(raw_card):
    out_card = {}
    fields = {
     "artist", \
     "borderColor", \
     "colorIdentity", \
     "colorIndicator", \
     "colors", \
     "convertedManaCost", \
     "duelDeck", \
     "faceConvertedManaCost", \
     "flavorText", \
     "foreignData", \
     "frameEffect", \
     "frameVersion", \
     "hand", \
     "hasFoil", \
     "hasNonFoil", \
     "isAlternative", \
     "isOnlineOnly", \
     "isOversized", \
     "isReserved", \
     "isStarter", \
     "isTimeshifted", \
     "layout", \
     "legalities", \
     "life", \
     "loyalty", \
     "manaCost", \
     "mcmId", \
     "mcmMetaId", \
     "mcmName", \
     "mciNumber", \
     "multiverseId", \
     "name", \
     "names", \
     "number", \
     "originalText", \
     "originalType", \
     "power", \
     "prices", \
     "printings", \
     "purchaseUrls", \
     "rarity", \
     "rulings", \
     "scryfallId", \
     "scryfallOracleId", \
     "scryfallIllustrationId", \
     "side", \
     "subtypes", \
     "supertypes", \
     "tcgplayerProductId", \
     "tcgplayerPurchaseUrl", \
     "text", \
     "toughness", \
     "type", \
     "types", \
     "uuid", \
     "variations", \
     "watermark" }
    for field in fields:
        if field in raw_card:
            out_card[field] = raw_card[field]
            if isinstance(out_card[field], list):
                out_card[field] = str(", ".join([
                    str(out_card[field][x])
                    for x in range(len(out_card[field]))
                ]))
        else:
            out_card[field] = ""

    def format_HTML(text):
        text = HTMLParser().unescape(smartypants.smartypants(text))
        return text

    #\ out_card['name'] = format_HTML(out_card['name'])
    # out_card['text'] = format_HTML(out_card['text'])
    # out_card['flavor'] = format_HTML(out_card['flavor'])
    return out_card


@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('\033[92m\033[1mInitialized the database.\033[0m')

@app.cli.command('reset_decks')
def initdb_command():
    warning = input('This will delete all decks. Are you sure? y/n   ')
    if warning == 'y':
        db = get_db()
        with app.open_resource('schema_decks.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    print('All decks removed successfully.')

@app.cli.command('import_cards')
def import_cards():
    init_db()
    print('\033[92m\033[1mInitialized the database.\033[0m')
    db = get_db()
    json_files = [
        pos_json for pos_json in os.listdir(PATH_TO_JSON)
        if pos_json.endswith('.json')
    ]
    for file in json_files:
        print(file)
        with open(os.path.join(PATH_TO_JSON, file)) as json_file:
            set_data = json.load(json_file)
            for set in set_data:
                set = set_data[set]
                set = format_set(set)
                print(set['name'])
                print('Importing ' + set['name'] + '...')
                import_sets_query = "INSERT INTO 'sets' (baseSetSize, block, boosterV3, code, codeV3, isFoilOnly, isOnlineOnly, keyruneCode, mcmName, mcmId, meta, mtgoCode, name, parentCode, releaseDate, tcgplayerGroupId, tokens, totalSetSize, translations, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
                db.execute(import_sets_query, \
                (set["baseSetSize"], \
                set["block"], \
                str(set["boosterV3"]), \
                set["code"], \
                set["codeV3"], \
                set["isFoilOnly"], \
                set["isOnlineOnly"], \
                set["keyruneCode"], \
                set["mcmName"], \
                set["mcmId"], \
                str(set["meta"]), \
                set["mtgoCode"], \
                set["name"], \
                set["parentCode"], \
                set["releaseDate"], \
                set["tcgplayerGroupId"], \
                str(set["tokens"]), \
                set["totalSetSize"], \
                str(set["translations"]), \
                set["type"]))
                for card in set['cards']:
                    card = format_card(card)
                    query = "INSERT INTO `cards` (artist, borderColor, colorIdentity, colorIndicator, colors, convertedManaCost, duelDeck, faceConvertedManaCost, flavorText, foreignData, frameEffect, frameVersion, hand, hasFoil, hasNonFoil, isAlternative, isOnlineOnly, isOversized, isReserved, isStarter, isTimeshifted, layout, legalities, life, loyalty, manaCost, mcmId, mcmMetaId, mcmName, multiverseId, name, names, number, originalText, originalType, power, prices, printings, purchaseUrls, rarity, releaseDate, rulings, scryfallId, scryfallOracleId, scryfallIllustrationId, setCode, setId, side, subtypes, supertypes, tcgplayerProductId, tcgplayerPurchaseUrl, text, toughness, type, types, uuid, variations, watermark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
                    db.execute(query, \
                        (card["artist"], \
                        card["borderColor"], \
                        card["colorIdentity"], \
                        card["colorIndicator"], \
                        card["colors"], \
                        card["convertedManaCost"], \
                        card["duelDeck"], \
                        card["faceConvertedManaCost"], \
                        card["flavorText"], \
                        card["foreignData"], \
                        card["frameEffect"], \
                        card["frameVersion"], \
                        card["hand"], \
                        card["hasFoil"], \
                        card["hasNonFoil"], \
                        card["isAlternative"], \
                        card["isOnlineOnly"], \
                        card["isOversized"], \
                        card["isReserved"], \
                        card["isStarter"], \
                        card["isTimeshifted"], \
                        card["layout"], \
                        str(card["legalities"]), \
                        card["life"], \
                        card["loyalty"], \
                        card["manaCost"], \
                        card["mcmId"], \
                        card["mcmMetaId"], \
                        card["mcmName"], \
                        card["multiverseId"], \
                        card["name"], \
                        card["names"], \
                        card["number"], \
                        card["originalText"], \
                        card["originalType"], \
                        card["power"], \
                        str(card["prices"]), \
                        card["printings"], \
                        str(card["purchaseUrls"]), \
                        card["rarity"], \
                        set["releaseDate"], \
                        card["rulings"], \
                        card["scryfallId"], \
                        card["scryfallOracleId"], \
                        card["scryfallIllustrationId"], \
                        set["code"], \
                        set["name"],
                        card["side"], \
                        card["subtypes"], \
                        card["supertypes"], \
                        card["tcgplayerProductId"], \
                        card["tcgplayerPurchaseUrl"], \
                        card["text"], \
                        card["toughness"], \
                        card["type"], \
                        card["types"], \
                        card["uuid"], \
                        card["variations"], \
                        card["watermark"]))
                    db.commit()
                    print(str(card['multiverseId']) + ' ' + card['name'])
            print('All cards successfully imported.')


@app.route('/show_entries/<setId>')
def show_entries(setId):
    flask_login.login_user(current_user)
    db = get_db()
    cur_cards = db.execute('select * from cards where setId like "%' + setId +
                           '%" order by uuid asc')
    cur_sets = db.execute('select *, block from sets where name like "%' +
                          setId + '%" order by releaseDate desc')
    cards = cur_cards.fetchall()
    sets = cur_sets.fetchall()
    return render_template('show_entries.html', cards=cards, sets=sets)


@app.route('/decks/', defaults={'page': 1})
@app.route('/decks/<int:page>')
def decks(page):
    flask_login.login_user(current_user)
    PER_PAGE = 36
    db = get_db()
    cur_count = db.execute('select count(*) from decks')
    count = cur_count.fetchone()[0]
    cur_decks = db.execute('select * from decks order by likes desc limit ' +
                           str(PER_PAGE) + ' offset ' + str(PER_PAGE * page -
                                                            PER_PAGE))
    pagination = Pagination(page, PER_PAGE, count)
    cur_sets = db.execute(
        'select * from sets order by releaseDate desc limit 5')
    decks = cur_decks.fetchall()
    sets = cur_sets.fetchall()
    legality = {}
    tags = {}
    makeup = {}
    for deck in decks:
        makeup[deck["id"]] = deck["makeup"].split(', ')
        deck_tags = deck["tags"]
        deck_tags = deck_tags.split(', ')
        tags[deck["id"]] = deck_tags
        deck_legality = deck["legality"]
        deck_legality = deck_legality.split(', ')
        legality[deck["id"]] = deck_legality

    return render_template(
        'decks.html',
        decks=decks,
        sets=sets,
        tags=tags,
        makeup=makeup,
        legality=legality,
        pagination=pagination)


@app.route('/cards/', defaults={'page': 1})
@app.route('/cards/<int:page>')
def cards(page):
    flask_login.login_user(current_user)
    filter_name = request.args.get('name')
    filter_set = request.args.get('set')
    filter_subtype = request.args.get('subtype')
    filter_type = request.args.get('type')
    sql_query = 'FROM cards WHERE uuid != "" AND supertypes != "Basic" AND multiverseId != ""'
    if filter_name:
        sql_query = sql_query + ' AND name LIKE "%' + filter_name + '%"'
    if filter_set:
        sql_query = sql_query + ' AND setCode = "' + filter_set.upper() + '"'
    if filter_type:
        sql_query = sql_query + ' AND type LIKE "%' + filter_type + '%"'
    if filter_subtype:
        sql_query = sql_query + ' AND subtypes LIKE "%' + filter_subtype + '%"'
    db = get_db()
    if filter_name or filter_set or filter_subtype or filter_type:
        cur_count = db.execute('SELECT COUNT(*) ' + sql_query)
        count = cur_count.fetchone()[0]
        cur_cards = db.execute(
            'SELECT * ' + sql_query + ' ORDER BY uuid DESC LIMIT ' +
            str(PER_PAGE) + ' offset ' + str(PER_PAGE * page - PER_PAGE))
        cards = cur_cards.fetchall()
        cur_sets = db.execute('SELECT * FROM sets')
    else:
        cur_count = db.execute(
            'SELECT COUNT(*) FROM cards WHERE supertypes != "Basic" AND hasNonFoil="1"'
        )
        count = cur_count.fetchone()[0]
        cur_cards = db.execute(
            'SELECT * FROM cards WHERE supertypes != "Basic" AND hasNonFoil = "1" ORDER BY "releaseDate" DESC, "number" ASC LIMIT '
            + str(PER_PAGE) + ' offset ' + str(PER_PAGE * page - PER_PAGE))
        cur_sets = db.execute(
            'SELECT * FROM sets WHERE tcgplayerGroupId != "" ORDER BY releaseDate DESC LIMIT 5')
        cards = cur_cards.fetchall()
    pagination = Pagination(page, PER_PAGE, count)
    card_mana = {}
    for card in cards:
        mana = card["manaCost"]
        mana = mana.replace('}{', ' ')
        mana = mana.replace('{', '')
        mana = mana.replace('}', '')
        mana = mana.replace('/', '')
        card_mana[card["id"]] = mana
    card_text = {}
    for card in cards:
        text = card["text"]
        # Italicize ability words
        text = re.compile(r'(((' + '|'.join(ABILITY_WORDS) + ')\s*?)+)',
                          re.I).sub(r'<em>\1</em>', text)
        # Making keyword abilities links so they can be used for tooltips and to
        # link to the glossary eventually
        text = re.compile(
            r'(((' + '|'.join(KEYWORD_ABILITIES) + ')\s*?)+)', re.I
        ).sub(
            r'<span class="tooltip" href="tooltip" title="Keyword Ability: \1">\1</span>',
            text)
        # Convert mana symbols to styled span elements
        text = text.replace('{', '<span class="mana small shadow s')
        text = text.replace('}', '">&nbsp;</span>')
        # Text on cards in parentheses is always italicized
        text = text.replace('(', '<em class="card-explanation">(')
        text = text.replace(')', ')</em>')
        text = text.replace('sW/U', 'swu')
        text = text.replace('sW/B', 'swb')
        text = text.replace('sU/B', 'sub')
        text = text.replace('sU/R', 'sur')
        text = text.replace('sB/R', 'sbr')
        text = text.replace('sB/G', 'sbg')
        text = text.replace('sR/W', 'srw')
        text = text.replace('sR/G', 'srg')
        text = text.replace('sG/W', 'sgw')
        text = text.replace('sG/U', 'sgu')
        text = text.replace('sW/P', 'swp')
        text = text.replace('sU/P', 'sup')
        text = text.replace('sB/P', 'sbp')
        text = text.replace('sR/P', 'srp')
        text = text.replace('sG/P', 'sgp')
        # Convert new lines to html line breaks
        text = Markup('</p><p>'.join(text.split('\n')))
        card_text[card["id"]] = text
    sets = cur_sets.fetchall()
    query_string = request.query_string
    return render_template(
        'cards.html',
        cards=cards,
        sets=sets,
        card_mana=card_mana,
        card_text=card_text,
        pagination=pagination,
        query_string=query_string,
        filter_set=filter_set,
        filter_type=filter_type,
        filter_subtype=filter_subtype,
        filter_name=filter_name,
        card_types=CARD_TYPES)


@app.route('/card/<uuid>')
def card(uuid):
    flask_login.login_user(current_user)
    db = get_db()
    cur = db.execute('SELECT * FROM cards WHERE uuid="' + uuid
                     + '"')
    card = cur.fetchone()
    if not card:
        abort(404)
    card_name = card['name']
    cur_cards = db.execute(
        'SELECT uuid, scryfallId, setCode, number FROM cards WHERE name=(?) AND uuid != "" ORDER BY releaseDate DESC',
        (card_name, ))
    other_cards = cur_cards.fetchall()
    likes = {}
    images = {}
    names = {}
    legality = {}
    tags = {}
    decks = {}
    authors = {}
    makeup = {}
    for other_card in other_cards:
        cur_decks = db.execute(
            'SELECT DISTINCT decks.id, name, tags, legality, image, likes, author, makeup FROM decksToCards INNER JOIN decks ON deckId=decks.id WHERE cardId=(?) ORDER BY likes DESC',
            (other_card['scryfallId'], ))

        cur_decks = cur_decks.fetchall()
        for deck in cur_decks:
            names[deck["id"]] = deck["name"]
            authors[deck["id"]] = deck["author"]
            likes[deck["id"]] = deck["likes"]
            decks[deck["id"]] = deck["id"]
            images[deck["id"]] = deck["image"]
            deck_tags = deck["tags"]
            deck_tags = deck_tags.split(', ')
            tags[deck["id"]] = deck_tags
            deck_legality = deck["legality"]
            deck_legality = deck_legality.split(', ')
            legality[deck["id"]] = deck_legality
            makeup[deck["id"]] = deck["makeup"].split(", ")
            print(deck)
    card_number = card['number']
    # Use card['layout'] instead of this jank
    flip_card_a = False
    flip_card_b = False
    if re.search('[a]', str(card_number)):
        flip_card_a = True
    if re.search('[b]', str(card_number)):
        flip_card_b = True
    card_mana = card['manaCost']
    card_mana = card_mana.replace('}{', ' ')
    card_mana = card_mana.replace('{', '')
    card_mana = card_mana.replace('}', '')
    card_mana = card_mana.replace('/', '')
    card_text = card["text"]
    # Italicize ability words
    card_text = re.compile(r'(((' + '|'.join(ABILITY_WORDS) + ')\s*?)+)',
                           re.I).sub(r'<em>\1</em>', card_text)
    # Making keyword abilities links so they can be used for tooltips and to
    # link to the glossary eventually
    card_text = re.compile(
        r'(((' + '|'.join(KEYWORD_ABILITIES) + ')\s*?)+)', re.I).sub(
            r'<a href="tooltip" title="Keyword Ability: \1">\1</a>', card_text)
    # Convert mana symbols to styled span elements
    card_text = card_text.replace('{', '<span class="mana medium shadow s')
    card_text = card_text.replace('}', '">&nbsp;</span>')
    # Text on cards in parentheses is always italicized
    card_text = card_text.replace('(', '<em class="card-explanation">(')
    card_text = card_text.replace(')', ')</em>')
    card_text = card_text.replace('sW/U', 'swu')
    card_text = card_text.replace('sW/B', 'swb')
    card_text = card_text.replace('sU/B', 'sub')
    card_text = card_text.replace('sU/R', 'sur')
    card_text = card_text.replace('sB/R', 'sbr')
    card_text = card_text.replace('sB/G', 'sbg')
    card_text = card_text.replace('sR/W', 'srw')
    card_text = card_text.replace('sR/G', 'srg')
    card_text = card_text.replace('sG/W', 'sgw')
    card_text = card_text.replace('sG/U', 'sgu')
    card_text = card_text.replace('sW/P', 'swp')
    card_text = card_text.replace('sU/P', 'sup')
    card_text = card_text.replace('sB/P', 'sbp')
    card_text = card_text.replace('sR/P', 'srp')
    card_text = card_text.replace('sG/P', 'sgp')
    # Convert new lines to html line breaks
    card_text = Markup('</p><p>'.join(card_text.split('\n')))
    card_flavor = card['flavorText']
    card_flavor = Markup('</p><p>'.join(card_flavor.split('\n')))
    return render_template(
        'card.html',
        card=card,
        card_text=card_text,
        card_mana=card_mana,
        card_flavor=card_flavor,
        flip_card_a=flip_card_a,
        flip_card_b=flip_card_b,
        decks=decks,
        other_cards=other_cards,
        legality=legality,
        tags=tags,
        names=names,
        likes=likes,
        images=images,
        authors=authors,
        makeup=makeup)


@app.route('/deck/<id>')
def deck(id):
    flask_login.login_user(current_user)
    db = get_db()
    cur = db.execute('SELECT * FROM decks WHERE id="' + id + '"')
    deck = cur.fetchone()
    
    print(deck['image'])
    if not deck:
        abort(404)
    cur = db.execute(
        'SELECT name, count(name), type, convertedManaCost, uuid, foil, featured, commander, layout, number, scryfallId, mainboard, sideboard, maybeboard, acquireboard FROM decksToCards INNER JOIN cards ON cardId=cards.scryfallId WHERE deckId="'
        + id + '" AND mainboard=1 GROUP BY name;')
    mainboard = cur.fetchall()
    cur = db.execute(
        'SELECT name, count(name), type, convertedManaCost, uuid, foil, featured, commander, layout, number, scryfallId, mainboard, sideboard, maybeboard, acquireboard FROM decksToCards INNER JOIN cards ON cardId=cards.scryfallId WHERE deckId="'
        + id + '" AND sideboard=1 GROUP BY name;')
    sideboard = cur.fetchall()
    cur = db.execute(
        'SELECT name, count(name), type, convertedManaCost, uuid, foil, featured, commander, layout, number, scryfallId, mainboard, sideboard, maybeboard, acquireboard FROM decksToCards INNER JOIN cards ON cardId=cards.scryfallId WHERE deckId="'
        + id + '" AND maybeboard=1 GROUP BY name;')
    maybeboard = cur.fetchall()
    cur = db.execute(
        'SELECT name, count(name), type, convertedManaCost, uuid, foil, featured, commander, layout, number, scryfallId, mainboard, sideboard, maybeboard, acquireboard FROM decksToCards INNER JOIN cards ON cardId=cards.scryfallId WHERE deckId="'
        + id + '" AND acquireboard=1 GROUP BY name;')
    acquireboard = cur.fetchall()
    convertedManaCost = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
    mainboard_count = {}
    sideboard_count = {}
    maybeboard_count = {}
    acquireboard_count = {}
    foil = {}
    commander = {}
    lands = {}
    planeswalkers = {}
    creatures = {}
    sorceries = {}
    instants = {}
    enchantments = {}
    artifacts = {}
    makeup = deck["makeup"].split(", ")
    for card in mainboard:
        if card['convertedManaCost'] == '':
            convertedManaCost[0] == convertedManaCost[0] + 1
        else:
            convertedManaCost[int(card['convertedManaCost'])] = convertedManaCost[int(card['convertedManaCost'])] + 1
        card_count = card[1]
        mainboard_count[card["uuid"]] = card_count
        card_foil = card['foil']
        foil[card["uuid"]] = card_foil
        card_commander = card['commander']
        if card_commander == 1:
            commander = card

        # Sort the cards by type
        if "Land" in card["type"]:
            lands[card['uuid']] = card
        if "Planeswalker" in card["type"]:
            planeswalkers[card['uuid']] = card
        if "Creature" in card["type"] and "Land" not in card["type"]:
            creatures[card['uuid']] = card
        if "Sorcery" in card["type"]:
            sorceries[card['uuid']] = card
        if "Instant" in card["type"]:
            instants[card['uuid']] = card
        if "Enchantment" in card["type"] and "Artifact" not in card[
                "type"] and "Creature" not in card["type"]:
            enchantments[card['uuid']] = card
        if "Artifact" in card["type"] and "Creature" not in card["type"]:
            artifacts[card['uuid']] = card


    for card in sideboard:
        card_count = card[1]
        sideboard_count[card["uuid"]] = card_count
    for card in maybeboard:
        card_count = card[1]
        maybeboard_count[card["uuid"]] = card_count
    for card in acquireboard:
        card_count = card[1]
        acquireboard_count[card["uuid"]] = card_count

    deck_image = deck["image"]
    deck_tags = deck["tags"]
    deck_tags = deck_tags.split(', ')
    deck_legality = deck["legality"]
    deck_legality = deck_legality.split(', ')

    def is_today(date):
        if (date == datetime.now().strftime("%B %d, %Y")):
            date = "today"
            return date
        else:
            return date

    def format_date(date):
        date = datetime.strptime(date, "%Y-%m-%d")
        date = date.strftime("%B %d, %Y")
        date = is_today(date)
        return date

    deck_created = format_date(deck["created"])
    deck_updated = format_date(deck["updated"])
    deck_description = deck["description"]
    # Convert new lines to html line breaks
    deck_description = Markup('</p><p>'.join(deck_description.split('\n')))
    print(commander)
    return render_template(
        'deck.html',
        lands=lands,
        planeswalkers=planeswalkers,
        creatures=creatures,
        sorceries=sorceries,
        instants=instants,
        enchantments=enchantments,
        artifacts=artifacts,
        deck=deck,
        mainboard=mainboard,
        mainboard_count=mainboard_count,
        sideboard=sideboard,
        sideboard_count=sideboard_count,
        maybeboard=maybeboard,
        maybeboard_count=maybeboard_count,
        acquireboard=acquireboard,
        acquireboard_count=acquireboard_count,
        foil=foil,
        makeup=makeup,
        deck_image=deck_image,
        deck_tags=deck_tags,
        deck_legality=deck_legality,
        deck_created=deck_created,
        deck_updated=deck_updated,
        commander=commander,
        deck_description=deck_description,
        convertedManaCost=convertedManaCost)


@app.route('/builder/', defaults={'id': False}, methods=['GET', 'POST'])
@app.route('/builder/<id>', methods=['GET', 'POST'])
def builder(id):
    flask_login.login_user(current_user)
    db = get_db()
    card_name = request.get_json()
    card_sets = {}
    card_release = {}
    edit_mode = False
    edit_name = ''
    edit_featured = ''
    edit_formats = ''
    edit_tags = ''
    edit_description = ''
    edit_cards = ''
    edit_sets = {}
    count = ''
    commander = ''
    foil = ''
    edit_id = ''
    edit_card = {
        'edit_names': [],
        'edit_sets': [],
        'edit_ids': [],
        'unique': []
    }
    edit_makeup = []
    if id:
        edit_id = id
        edit_mode = True
        edit_data = db.execute('SELECT * FROM decks WHERE id=' + id + ';')
        edit_data = edit_data.fetchone()
        edit_name = edit_data["name"]
        edit_featured = edit_data["image"]
        edit_formats = edit_data["formats"]
        edit_tags = edit_data["tags"]
        edit_description = edit_data["description"]
        cur = db.execute(
            'SELECT name, setId, count(name), type, colorIdentity, uuid, foil, featured, commander FROM decksToCards INNER JOIN cards ON cardId=cards.uuid WHERE deckId="'
            + id + '" GROUP BY name')
        edit_cards = cur.fetchall()
        count = {}
        foil = {}
        commander = {}
        for card in edit_cards:
            card_count = card[2]
            count[card["uuid"]] = card_count
            card_foil = card['foil']
            foil[card["uuid"]] = card_foil
            card_commander = card['commander']
            commander[card["uuid"]] = card_commander
            card_id = card["uuid"]
            if len(card["colorIdentity"]):
                edit_makeup.extend(card["colorIdentity"].split(', '))
            edit_sets_data = db.execute(
                'SELECT uuid, name, setId FROM cards WHERE name LIKE "'
                + HTMLParser().unescape(smartypants.smartypants(card[0])) +
                '" AND uuid != "" AND releaseDate == "" ORDER BY uuid DESC '
            )
            edit_sets = edit_sets_data.fetchall()
            for edit_set in edit_sets:
                edit_card['edit_names'].append(edit_set[1])
                edit_card['edit_ids'].append(str(edit_set[0]))
                edit_card['edit_sets'].append(edit_set[2])
            if edit_card['edit_names'].count(edit_set[1]) == 1:
                edit_card['unique'].append(True)
            else:
                edit_card['unique'].append(False)
    if card_name:
        card_name = card_name['cardName']
        card_data = db.execute(
            'SELECT uuid, setId, type, colorIdentity, scryfallId, releaseDate FROM cards WHERE name LIKE "'
            + card_name +
            '" AND uuid != "" ORDER BY releaseDate DESC '
        )
        card_data = card_data.fetchall()
        if card_data:
            card_id = ''
            card_return = { 'card_found': True }
            print(titlecase(card_name) + ' printings:')
            for i, card in enumerate(card_data, start=0):
                card_sets[card[0]] = str(card[1])
                print(str(i) + ': ' + card['setId'] + ' ' + str(card[4]) + ' ' + str(card[0]) + ' ' + card['releaseDate'])
                card_return[str(i)] = {
                    'card_id': str(card[0]),
                    'card_set': card['setId'],
                    'card_type': str(card[2]),
                    'card_makeup': str(card[3]),
                    'card_image': str(card[4]),
                }
            print(card_return)
            return card_return
        else:
            card_return = json.dumps({'card_found': False})
            return card_return
    return render_template(
        'builder.html',
        edit_mode=edit_mode,
        edit_id=edit_id,
        edit_name=edit_name,
        edit_formats=edit_formats,
        edit_featured=edit_featured,
        edit_tags=edit_tags,
        edit_makeup=edit_makeup,
        edit_description=edit_description,
        edit_cards=edit_cards,
        count=count,
        commander=commander,
        foil=foil,
        edit_card=edit_card)


@app.route('/add_deck', methods=['GET', 'POST'])
def add_deck():
    flask_login.login_user(current_user)
    deck = request.get_json()
    # Check if we're editing an existing deck
    if deck:
        deck_id = deck['edit_id']
        deck_description = deck['description']
        deck_formats = deck['formats']
        deck_legality = deck['formats']
        deck_tags = deck['tags']
        deck_name = titlecase(deck['name'].strip())
        deck_cards = deck['cards']
        deck_makeup = deck['makeup']
    # This needs to be set to the currently logged-in user.
    deck_author = "Casanova Killing Spree"
    # This needs to be calculated somehow.
    deck_colors = "{r}{b}"
    deck_makeup = deck['makeup']
    deck_makeup_length = len(deck_makeup)
    if deck_makeup_length != 0:
        deck_makeup_w = (float(deck_makeup.count('W')) / deck_makeup_length) * 100
        deck_makeup_u = (float(deck_makeup.count('U')) / deck_makeup_length) * 100
        deck_makeup_b = (float(deck_makeup.count('B')) / deck_makeup_length) * 100
        deck_makeup_r = (float(deck_makeup.count('R')) / deck_makeup_length) * 100
        deck_makeup_g = (float(deck_makeup.count('G')) / deck_makeup_length) * 100
        deck_makeup = str(deck_makeup_w) + ', ' + str(deck_makeup_u) + ', ' + str(
            deck_makeup_b) + ', ' + str(deck_makeup_r) + ', ' + str(deck_makeup_g)
    else:
        deck_makeup = "0.0, 0.0, 0.0, 0.0, 0.0"
    # This is based on the Featured image selected while building.
    deck_image = "414494"
    deck_likes = 0
    # These are probably obsolete.
    deck_mainboard = "main"
    deck_maybeboard = "maybe"
    deck_sideboard = "side"
    # Double checking form fields that should've been verified on the front-end.
    if deck_name == "":
        error = Markup("<strong>Oops!</strong>")
        flash(error + " Looks like your deck doesn't have a name.", 'error')
    elif deck_tags == "":
        error = Markup("<strong>Oops!</strong>")
        flash(error + " Looks like your deck doesn't have any tags.", 'error')
    elif deck_legality == "":
        error = Markup("<strong>Oops!</strong>")
        flash(error + " Looks like your deck isn't legal in any format.",
              'error')
    else:
        db = get_db()
        for card in deck_cards:
            if deck_cards[card]['featured'] == 1:
                deck_image = deck_cards[card]['image']
        if deck_id == '':
            cur_cards = db.execute(
                'INSERT INTO decks values (null, ?, ?, null, date("now"), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date("now"), ?)',
                (deck_author, deck_colors, deck_description, deck_formats,
                 deck_image, deck_legality, deck_likes, deck_mainboard,
                 deck_maybeboard, deck_name, deck_sideboard, deck_tags,
                 deck_makeup))

        else:
            cur_cards = db.execute(
                'UPDATE decks SET colors = ?, description = ?, formats = ?, image = ?, legality = ?, name = ?, tags = ?, updated = ? WHERE id = ?',
                (deck_colors, deck_description, deck_formats, deck_image,
                 deck_legality, deck_name, deck_tags,
                 time.strftime('%Y-%m-%d'), deck_id))

        deck_row = cur_cards.lastrowid
        if deck_id != '':
            db.execute('DELETE FROM decksToCards WHERE deckId=?', (deck_id, ))
        for card in deck_cards:
            quantity = deck_cards[card]['quantity']
            for i in range(int(quantity)):
                if deck_cards[card]['foil'] == 1:
                    card_foil = 1
                else:
                    card_foil = 0
                if deck_cards[card]['featured'] == 1:
                    card_featured = 1
                else:
                    card_featured = 0
                if deck_cards[card]['commander'] == 1:
                    card_commander = 1
                else:
                    card_commander = 0
                if deck_id == '':
                    db.execute('INSERT INTO decksToCards VALUES(NULL, ' + str(deck_row) + ', "' + deck_cards[card]['image'] + '", ' + str(card_foil) + ', ' + str(card_featured) + ', ' + str(card_commander) + ', 0, 0, 0, 1)')
                else:
                    db.execute(
                        'INSERT INTO decksToCards VALUES(NULL, ?, ?, ?, ?, ?, 0, 0, 0, 1);',
                        (deck_id, card, card_foil, card_featured,
                         card_commander))
                    db.execute(
                        'UPDATE decksToCards SET featured = 0 WHERE featured = 1;'
                    )
                    db.execute(
                        'UPDATE decksToCards SET foil = ?, featured = ?, commander = ? WHERE cardId = ?',
                        (card_foil, card_featured, card_commander, card))

            if deck_id == '':
                print("Inserted Multiverse ID " + card + " into Deck " + str(
                    deck_row) + " " + str(quantity) + " times.")
            else:
                print("Inserted Multiverse ID " + str(
                    card) + " into Deck " + str(deck_id) + " " + str(
                        quantity) + " times.")
        db.commit()
        return 'success'
    return redirect(url_for('decks'))


@app.route('/login')
def index():
    flask_login.login_user(current_user)
    return render_template('login.html')


@app.route('/settings')
def settings():
    flask_login.login_user(current_user)
    return render_template('settings.html')


@app.route('/appendices')
def appendices():
    flask_login.login_user(current_user)
    return render_template(
        'appendices.html',
        keyword_abilities=KEYWORD_ABILITIES,
        ability_words=ABILITY_WORDS,
        card_types=CARD_TYPES,
        formats=FORMATS)


@app.route('/')
@app.route('/grimoire')
def grimoire():
    flask_login.login_user(current_user)
    db = get_db()
    cur_count = db.execute('select count(*) from decks')
    count = cur_count.fetchone()[0]
    cur_decks = db.execute('select * from decks order by likes desc LIMIT 10')
    cur_sets = db.execute(
        'select * from sets limit 5')
    decks = cur_decks.fetchall()
    sets = cur_sets.fetchall()
    legality = {}
    tags = {}
    makeup = {}
    for deck in decks:
        deck_tags = deck["tags"]
        deck_tags = deck_tags.split(', ')
        tags[deck["id"]] = deck_tags
        deck_legality = deck["legality"]
        deck_legality = deck_legality.split(', ')
        legality[deck["id"]] = deck_legality
        makeup[deck["id"]] = deck["makeup"].split(', ')

    sql_query = 'FROM cards WHERE uuid != ""'
    cur_count = db.execute(
        'SELECT COUNT(*) FROM cards WHERE uuid != "" LIMIT 15'
    )
    count = cur_count.fetchone()[0]
    cur_cards = db.execute(
        'SELECT * FROM cards WHERE uuid != "" AND type LIKE "%Creature%" AND subtypes LIKE "%Frog%" ORDER BY uuid DESC'
    )
    cards = cur_cards.fetchall()
    card_mana = {}
    for card in cards:
        mana = card["manaCost"]
        mana = mana.replace('}{', ' ')
        mana = mana.replace('{', '')
        mana = mana.replace('}', '')
        mana = mana.replace('/', '')
        card_mana[card["id"]] = mana
    card_text = {}
    for card in cards:
        text = card["text"]
        # Italicize ability words
        text = re.compile(r'(((' + '|'.join(ABILITY_WORDS) + ')\s*?)+)',
                          re.I).sub(r'<em>\1</em>', text)
        # Making keyword abilities links so they can be used for tooltips and to
        # link to the glossary eventually
        text = re.compile(
            r'(((' + '|'.join(KEYWORD_ABILITIES) + ')\s*?)+)', re.I
        ).sub(
            r'<span class="tooltip" href="tooltip" title="Keyword Ability: \1">\1</span>',
            text)
        # Convert mana symbols to styled span elements
        text = text.replace('{', '<span class="mana small shadow s')
        text = text.replace('}', '">&nbsp;</span>')
        # Text on cards in parentheses is always italicized
        text = text.replace('(', '<em class="card-explanation">(')
        text = text.replace(')', ')</em>')
        text = text.replace('sW/U', 'swu')
        text = text.replace('sW/B', 'swb')
        text = text.replace('sU/B', 'sub')
        text = text.replace('sU/R', 'sur')
        text = text.replace('sB/R', 'sbr')
        text = text.replace('sB/G', 'sbg')
        text = text.replace('sR/W', 'srw')
        text = text.replace('sR/G', 'srg')
        text = text.replace('sG/W', 'sgw')
        text = text.replace('sG/U', 'sgu')
        text = text.replace('sW/P', 'swp')
        text = text.replace('sU/P', 'sup')
        text = text.replace('sB/P', 'sbp')
        text = text.replace('sR/P', 'srp')
        text = text.replace('sG/P', 'sgp')
        # Convert new lines to html line breaks
        text = Markup('</p><p>'.join(text.split('\n')))
        card_text[card["id"]] = text
    return render_template(
        'grimoire.html',
        decks=decks,
        sets=sets,
        tags=tags,
        legality=legality,
        makeup=makeup,
        cards=cards,
        card_mana=card_mana,
        card_text=card_text,
        card_types=CARD_TYPES)


@app.route('/delete_deck/<id>', methods=['GET', 'POST'])
def delete_deck(id):
    db = get_db()
    cur_deck_name = db.execute('SELECT name FROM decks WHERE id=?;', (id, ))
    cur_deck_name = cur_deck_name.fetchone()
    db.execute('DELETE FROM decks WHERE id=?;', (id, ))
    db.execute('DELETE FROM decksToCards where deckId=?;', (id, ))
    db.commit()
    flash(cur_deck_name[0] + ' was successfully deleted.', 'success')
    return redirect(url_for('decks'))


@app.errorhandler(404)
def page_not_found(e):
    flask_login.login_user(current_user)
    version = randint(0, 2)
    return render_template('404.html', version=version), 404
