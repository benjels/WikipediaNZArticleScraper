__author__ = 'user'

from bs4 import BeautifulSoup
import requests
import regex
import yaml
from pprint import pprint

#this is just debug shit
failedGets = set()



#an instance of the Harvester class can be used to find a lot of interesting URLs given an appropriate yml file
class Harvester(object):
    def __init__(self, ruleset, verbose = False):
        #debug shit
        self.gatheredCount = 0
        ###############
        self.WIKIPEDIA_URL_ROOT_STRING = "https://en.wikipedia.org"
        #TODO marked for deletion now that we are trying to identify lists in yml ...self.LIST_TITLE_PATTERN = "[^a-z|A-Z]list[^a-z|A-Z]|^list[^a-z|A-Z]|[^a-z|A-Z]list$|[^a-z|A-Z]lists[^a-z|A-Z]|^lists[^a-z|A-Z]|[^a-z|A-Z]lists$" #pattern that finds articles with lists/list as a discrete word in the article URL
        self.visitedURLs = set()
        self.FoundArticlesTitles = set()
        self.verbose = verbose
        with open(ruleset, "r") as fileStream:
            self.rules = yaml.load(fileStream)#dont actually know what will be encoded in the rules yaml. But probably something.

    #just used to start the searching. Calls findArticles
    def harvest(self):
        allFoundArticles = set()
        for seed, maxDepth in self.rules["seeds"].items():
            self.maxDepth = maxDepth
            allFoundArticles = allFoundArticles.union(self.findArticles(seed, 0))
        return allFoundArticles




    def findArticles(self, pageName, depth):
        returnSet = set()
        #check that we haven't gone too deep
        if depth >= self.maxDepth:
            print("we went 2deep at this page so we are stopping: " + pageName)
            return returnSet
        #mark this URL as visited so that we don't come back
        self.visitedURLs.add(pageName)
        articleSoup = self.getSoup(pageName)
        #if we failed to turn the href of this page into soup for some reason
        if articleSoup is None:
            failedGets.add(pageName)#TODO this is just for debug
            return returnSet
        #check whether we are at a list or leaf page
        articleIsCollection = False
        for eachRegion, regexs in self.rules["collectionArticleIdentifiers"].items():
            if any( regex.search(eachRegex, str(articleSoup.select(eachRegion)).lower()) for eachRegex in regexs):
                print("this article is a list:" + pageName)
                articleIsCollection = True
        if articleIsCollection:
            #if the listwe are at is topic-related, gather all of the list elements and make recursive calls with their hrefs
            if self.evaluateArticleRelatedness(articleSoup):
                    listEntries = self.gatherListEntries(articleSoup)
                    for eachListEntry in listEntries:
                        if eachListEntry not in self.visitedURLs:
                            returnSet = returnSet.union(self.findArticles(eachListEntry, depth + 1))
        #if we are at a leaf, then check whether we want to return this as relevant or not
        else:
           if self.evaluateArticleRelatedness(articleSoup):
               print("gathered - " + pageName + " No." + str(self.gatheredCount))
               self.gatheredCount+=1
               returnSet.add(self.cleanTitle(pageName))

        #at this point return set either has (a): one or more relevant article URLs, (b) nothing in it because it was a leaf article but not relevant
        return returnSet

        #helper method used to find list elements on a list article page
    def gatherListEntries(self, articleSoup):
        listElements = set()
        #get the hrefs that lie inside of our scopes
        print("harvisting the list elemetns")
        for eachPattern in self.rules["scopes"]:
            print("now using the rule: " + eachPattern)
            foundElements = articleSoup.select(eachPattern) #i need to use findAll here not select because findAll works with anchor text identifier which are needed to get htose hrefs labeld as "next" so fuck
            print(" the tags that we found when finding list entries were: " + str(foundElements))
            for eachElement in foundElements:
                listElements.add(eachElement.get("href"))
        #filter out the hrefs that don't meet our listEntryRequirements
        goodElements = set()
        for eachHref in listElements:
            if all( regex.search(eachRegex, eachHref) for eachRegex in self.rules["listEntryRequirements"]) and not any( regex.search(eachRegex, eachHref) for eachRegex in self.rules["listEntryDissaloweds"] ):
                print("adding " + eachHref + " to the list of good elements")
                goodElements.add(eachHref)
            else:
                print("didnt add " + eachHref + " to the list of good elements")

        return goodElements

        #TODO: a good idea for the black list is probably to check that wgCategories field. That said, we probably don't mind having some articles that are in the e.g. Australia category. Really, if an australian article has enough new zealandness to be confused with a new zealand article, we might want it...
    #takes beautiful soup of a wikipedia article and uses its instance's rules.yml to determine whether it is an interesting article or not.
    #if it is, return true, else return false
    def evaluateArticleRelatedness(self, articleSoup):
        #check for black list matches in the black listed areas (delineated by regex expressions and css selectors in rules.yml)
        #return False if match found
        for eachBadScope, badStrings in self.rules["blacklist"].items():
            searchRegion = articleSoup.select(eachBadScope)
            searchRegion = str(searchRegion).lower()
            for eachBadString in badStrings:
                if eachBadString in searchRegion:
                    return False

#so the bug is that when it doesnt find any of the good strings in the first scope, it doesnt check any of the other scopes...
        #check for  white list matches in the interesting areas
        #return true if match found
        for eachGoodScope, goodStrings in self.rules["whitelist"].items():
            searchRegion = articleSoup.find(eachGoodScope)
            searchRegion = str(searchRegion).lower()
            for eachGoodString in goodStrings:
                print("looking for the regex:" + eachGoodString + " in the string: " + searchRegion)
                if eachGoodString in searchRegion:
                    return True
        #return False (no black list matches but no interesting stuff found either)
        print("nah found no white listed stuff here")
        return False;





    #just a helper method for getting the text content from a wikipedia page name (e.g. "List_of_towns_in_New_Zealand")
    #Returns the text content of the page queried UNLESS there is an error, then returns None.
    def getSoup(self, pageName):
        url = self.WIKIPEDIA_URL_ROOT_STRING + pageName
        if self.verbose:
            print("getting : " + url)
        response = requests.get(url)#TODO: probably also catch all exceptions raised by making the request and just log the URLs that cause them
        if response.status_code != 200:
            print("error making request. status code: " + str(response.status_code))
            print(url)
            return None
        return BeautifulSoup(response.text, 'html.parser')


    #TODO: i think i need to account for ' as well which is becing reincoded incorrectly
    def cleanTitle(self, urlExtension):
        #remove "wiki" prefix
        title = urlExtension[6:]
        #swap out _ for " "
        title = title.replace("_", " ").lower()
        print("TITLE IDed AS:" + title)
        return title






def main():
     harvester = Harvester( "rules.yml", verbose=True)
     setOfHarvestedTitle = harvester.harvest()
     for eachTitle in setOfHarvestedTitle:
         print("-" + eachTitle +"|")
     print("so we gathered the following amount of articles: " + str(len(setOfHarvestedTitle)))
     for each in failedGets:
         print("failed: " + each)
     with open("ifWellingtonNotInHereItBecauseOtherSeedMessesItUp.txt", "w") as outFile:
         setOfHarvestedTitle = "\n".join(setOfHarvestedTitle)
         outFile.writelines(setOfHarvestedTitle)
if __name__ == '__main__':
    main()

# todo:

# -change logic for determining whether an article is a list or not. some lists have names without "list" in them e.g. "Presidents of the U.S.A." TRY TO FIND SOME SEMANTIC MARKER IN THE WIKIPEDIA ARTICLE HTML. also try to make those pages that each hold 200 links lists and make that href that goes to the next 200 a list link. That way can get those ~8000 ez wikipedia pages just through using this program
# -make determining nzness more sophisticated in the yml :)
#- a character in e.g. "maori" id like /wiki/M%C4%81ori_language should be /wiki/Maori_language
#-add listness as a list of regexs in the yml. should have that existing list/lists one and "Category:" as well
#-there are some wikipedia articles that SHOULD be getting gathered but dont seem to be getting got in the whitelist check step open in chrome :) have a nice day