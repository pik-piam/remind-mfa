# The flodym library

REMIND-MFA is built on the newly developed flodym software library, which offers flexibility and performance improvements over existing MFA libraries like ODYM (Pauliuk & Heeren, 2020).
The most important novelties of flodym are:

* A FlodymArray object which manages the multi-dimensional operations of one or several arrays such as flows, stocks, parameters, or trades, based on the dimensions given at initialisations. This allows to change the number or order of dimensions, and the number and order of items in each dimension, with minimal changes to the code.
* Integrating the data structures for handling a material stock based on a lifetime model with those of the whole MFA system (they were two separate entities in ODYM), and making them work on multi-dimensional arrays instead of just scalars. This has benefits for code simplicity and performance.
* A simplified, more flexible, and much more performant data read-in
* Visualisation and export routines (all the result figures in this report are created with flodym visualisation routines).
* An extended functionality with respect to dynamic stock models and lifetime models
* [Extensive documentation](https://flodym.readthedocs.io/)

The [EU-MFA](https://transience-eu-mfa.readthedocs.io/) developed within the TRANSIENCE project with European scope also builds on flodym, which paves the way to a close code integration of both MFA models within MIC3.