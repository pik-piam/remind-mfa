## World Steel Database

PIK has a subscription to the up
to-date [World Steel Association's (WSA) database](https://worldsteel.org/my-account/?redirect=https://worldsteel.org/data/restricted-area/),
which contains the most recent data on e.g. steel production and trade.

Data is given on a country level and is roughly available from 2001 to 2022,
differing slightly between the datasets. This might be updated regularly. Access is handled by Dr. Jakob Dürrwächter.
Data can be downloaded in Excel sheets and is stored on the PIK cluster for internal
usage and preparation for SIMSON.

The database contains information on various flows in the global steel cycle. This is often classified and designed
differently. For more information on definitions of the mentioned categories, please refer to
the [Overview](../overview.md) page. Sadly, the WSA does not provide in depth information on how the data was gathered,
and what the datasets entail exactly. Some information can be found in
the [WSA's Glossary](https://worldsteel.org/about-steel/glossary/#:~:text=True%20steel%20use%20(TSU)%20is,indirect%20trade%20in%20steel%20calculations.)

The datasets (marked **bold** below) are available in the categories production, trade and use.

### Production

- **Crude**: Total crude steel production
    - Crude steel production by process
        - **BOF**: Basic Oxygen Furnace, sometimes also called OBC (Oxygen Blown Converter) roughly 74 %
        - **EAF**: Electric Arc Furnace, roughly 25 %
        - **Other** (*"otherproc"*): Other processes, made up mostly of the open hearth furnace (OHF) production,
          roughly 0.5 %
    - Crude steel production by cast type
        - **Ingots**: Production of ingots (steel bars), roughly 4 %
        - **Continuous casting** (*"ccast"*): Production of continously cast steel products, roughly 96 %
        - **Liquid steel casting** (*"licast"*): Production of liquid steel, roughly 0.2 %
- Finished steel products (formed/processed out of continously cast steel products and ingots; some of the production
  types are subtypes of others, see
  the [Overview](../overview.md))
    - **Hot rolled products**
    - **Hot rolled long products**
    - **Hot rolled flat products**
    - **Tracks**
    - **Heavy sections**
    - **Light sections**
    - **Reinforement bars**, also called rebar
    - **Hot rolled bars other than rebar** (*"hotrollednonrebar""*)
    - **Wire rod**
    - **Hot rolled plate**
    - **Hot rolle coil**
    - **Electrical sheet**(*"elsheet"*)
    - **Tin mill products**
    - **Other metallic coated sheet & strip** (*"othersheet_metcoat"*): mostly galvanised products
    - **Other non-metallic coated sheet & strip** (*"othersheet_nonmetcoat"*)
    - **Tubular products**
    - **Seamless tubes**
    - **Welded tubes**
- Production of materials used in steel production
    - **Pig iron**: Production of pig iron, which is mostly used in the BOF process
    - **Direct reduced iron**: Production of DRI, which is mostly used in the EAF process
    - **Iron ore**: Production of iron ore, which is used to make pig iron

### Trade

All trade datasets have an **imports** and an **exports** Excel sheet

- **Finished steel products**: Total trade of all aforementioned finished steel products
- **Ingots**
- **Long products**
- **Flat products**
- **Tubular products**
- **Pig iron**
- **Direct reduced iron**
- **Iron ore**
- **Scrap**: Trade of scrap, which is then used mostly in the EAF process but also in the BOF production route
- **Indirect Trade**: Indirect trade is trade of final products containing steel, like cars and machinery. It can occur
  right after production or after some years of use. In the database folder, these sheets are marked with a leading 'I'
  rather than a 'T' like in the other trade datasets

### Use

Steel use is given as an estimate by the World Steel Association. *Apparent steel use (ASU)* is defined as production
plus
imports and minus exports of finished steel products. It is given in *crude and finished steel equivalent*, as there are
some losses in the production route. Also, *true steel use (TSU)* defined as ASU plus net indirect trade is provided.
All use data is given as total and per capita. Hence, the final datasets are:

- **Apparent steel use (*crude steel equivalent*)**
- **Apparent steel use per capita (*crude steel equivalent*)**
- **Apparent steel use (*finished steel equivalent*)**
- **Apparent steel use per capita (*finished steel equivalent*)**
- **True steel use**: Total true steel use
- **True steel use per capita**: True steel use divided by the population of the country